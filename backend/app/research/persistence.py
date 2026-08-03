from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import JSON, DateTime, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .engine import DeterministicReplayEngine, make_strategy, monte_carlo_resample, parameter_combinations, walk_forward_windows
from .events import EventDatasetCatalog


class ExperimentConfig(BaseModel):
    dataset_id: str
    strategy: str
    starting_cash: float = Field(default=100_000.0, gt=0)
    timer_interval_ms: int = Field(default=1_000, ge=1)
    base_parameters: dict[str, Any] = Field(default_factory=dict)
    parameter_grid: dict[str, list[Any]] = Field(default_factory=dict)
    walk_forward_folds: int = Field(default=4, ge=1, le=20)
    monte_carlo_runs: int = Field(default=500, ge=0, le=20_000)
    monte_carlo_block_size: int = Field(default=5, ge=1, le=10_000)
    seed: int = 7


class ExperimentView(BaseModel):
    id: str
    status: str
    config: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class ExperimentStore:
    def __init__(self, database_url: str | None = None) -> None:
        class Base(DeclarativeBase):
            pass

        class Record(Base):
            __tablename__ = "quantforge_experiments"
            id: Mapped[str] = mapped_column(String(64), primary_key=True)
            status: Mapped[str] = mapped_column(String(32), index=True)
            config: Mapped[dict[str, Any]] = mapped_column(JSON)
            result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
            error: Mapped[str | None] = mapped_column(Text, nullable=True)
            created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
            updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

        url = database_url or os.getenv("DATABASE_URL", "sqlite:///./quantforge.sqlite3")
        self.engine = create_engine(url, pool_pre_ping=True)
        self.Record = Record
        self.Session = sessionmaker(self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

    def create(self, config: ExperimentConfig) -> ExperimentView:
        now = datetime.now(timezone.utc)
        record = self.Record(id=uuid.uuid4().hex, status="queued", config=config.model_dump(mode="json"), result=None, error=None, created_at=now, updated_at=now)
        with self.Session.begin() as session:
            session.add(record)
        return self._view(record)

    def get(self, experiment_id: str) -> ExperimentView:
        with self.Session() as session:
            record = session.get(self.Record, experiment_id)
            if not record:
                raise KeyError(experiment_id)
            return self._view(record)

    def list_recent(self, limit: int = 25) -> list[ExperimentView]:
        safe_limit = max(1, min(limit, 100))
        with self.Session() as session:
            records = session.scalars(
                select(self.Record).order_by(self.Record.created_at.desc()).limit(safe_limit)
            ).all()
            return [self._view(record) for record in records]

    def set_status(self, experiment_id: str, status: str, result: dict[str, Any] | None = None, error: str | None = None) -> ExperimentView:
        with self.Session.begin() as session:
            record = session.get(self.Record, experiment_id)
            if not record:
                raise KeyError(experiment_id)
            record.status = status
            record.result = result
            record.error = error
            record.updated_at = datetime.now(timezone.utc)
        return self._view(record)

    @staticmethod
    def _view(record: Any) -> ExperimentView:
        return ExperimentView(id=record.id, status=record.status, config=record.config, result=record.result, error=record.error, created_at=record.created_at, updated_at=record.updated_at)


def enqueue_experiment(experiment_id: str) -> str:
    from redis import Redis
    from rq import Queue

    connection = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))
    job = Queue("quantforge", connection=connection, default_timeout=3600).enqueue("app.research.persistence.run_experiment_job", experiment_id, job_timeout=3600)
    return job.id


def run_experiment_job(experiment_id: str) -> dict[str, Any]:
    store = ExperimentStore()
    view = store.set_status(experiment_id, "running")
    config = ExperimentConfig.model_validate(view.config)
    try:
        result = run_experiment(config)
    except Exception as exc:
        store.set_status(experiment_id, "failed", error=str(exc))
        raise
    store.set_status(experiment_id, "completed", result=result)
    return result


def run_experiment(config: ExperimentConfig) -> dict[str, Any]:
    events = EventDatasetCatalog().read(config.dataset_id)
    if not events:
        raise ValueError("Dataset contains no events")
    windows = walk_forward_windows(len(events), config.walk_forward_folds)
    candidates: list[dict[str, Any]] = []
    for parameters in parameter_combinations(config.base_parameters, config.parameter_grid):
        replay_engine = DeterministicReplayEngine(
            timer_interval_ms=config.timer_interval_ms,
            fee_bps=float(parameters.get("fee_bps", 2.0)),
        )
        folds: list[dict[str, Any]] = []
        returns: list[float] = []
        for fold_index, (_, test_slice) in enumerate(windows):
            test_events = events[test_slice]
            if not test_events:
                continue
            replay = replay_engine.run(test_events, make_strategy(config.strategy, parameters), config.starting_cash)
            returns.append(replay.return_pct / 100)
            folds.append({"fold": fold_index, "event_count": replay.event_count, "return_pct": replay.return_pct, "max_drawdown_pct": replay.max_drawdown_pct, "fill_count": replay.fill_count})
        score = sum(returns) / len(returns) if returns else -1e100
        candidates.append({"parameters": parameters, "score": score, "folds": folds, "monte_carlo": monte_carlo_resample(returns, runs=config.monte_carlo_runs, block_size=config.monte_carlo_block_size, seed=config.seed)})
    candidates.sort(key=lambda candidate: candidate["score"], reverse=True)
    return {"dataset_id": config.dataset_id, "strategy": config.strategy, "candidate_count": len(candidates), "best": candidates[0] if candidates else None, "candidates": candidates}
