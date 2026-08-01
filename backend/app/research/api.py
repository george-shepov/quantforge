from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .engine import DeterministicReplayEngine, make_strategy
from .events import EventDatasetCatalog, RecorderConfig, RecorderManager
from .execution import HyperliquidTestnetAdapter, TestnetOrderRequest, TestnetSafetyGate
from .persistence import ExperimentConfig, ExperimentStore, enqueue_experiment

router = APIRouter(prefix="/api/research", tags=["event research"])
catalog = EventDatasetCatalog(os.getenv("QUANTFORGE_DATA_ROOT", "./data/quantforge"))
recorders = RecorderManager(catalog)


@lru_cache(maxsize=1)
def experiment_store() -> ExperimentStore:
    return ExperimentStore()


class ReplayRequest(BaseModel):
    dataset_id: str
    strategy: str = "cross_exchange_arbitrage"
    parameters: dict[str, Any] = Field(default_factory=dict)
    starting_cash: float = Field(default=100_000.0, gt=0)
    timer_interval_ms: int = Field(default=1_000, ge=1, le=3_600_000)


@router.get("/capabilities")
def capabilities() -> dict[str, Any]:
    return {
        "market_data": ["hyperliquid_l2_book", "hyperliquid_trades", "hyperliquid_all_mids", "hyperliquid_funding"],
        "datasets": ["partitioned_parquet", "manifest_catalog", "checksum_chain", "deterministic_replay"],
        "strategy_callbacks": ["on_book", "on_trade", "on_funding", "on_timer"],
        "portfolio": ["multi_asset", "multi_exchange", "cross_exchange_arbitrage"],
        "research": ["parameter_sweeps", "walk_forward", "block_monte_carlo"],
        "microstructure": ["inventory_skew", "queue_position"],
        "persistence": ["postgresql", "redis_rq_worker"],
        "execution": TestnetSafetyGate().status(),
    }


@router.post("/recordings", status_code=202)
async def start_recording(config: RecorderConfig) -> dict[str, Any]:
    return recorders.start(config)


@router.get("/recordings")
def recording_status() -> Any:
    return recorders.status()


@router.get("/recordings/{dataset_id}")
def one_recording_status(dataset_id: str) -> Any:
    try:
        return recorders.status(dataset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Recording not found") from exc


@router.delete("/recordings/{dataset_id}")
async def stop_recording(dataset_id: str) -> dict[str, Any]:
    try:
        return await recorders.stop(dataset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Recording not found") from exc


@router.get("/datasets")
def datasets() -> list[dict[str, Any]]:
    return [manifest.model_dump(mode="json") for manifest in catalog.list()]


@router.get("/datasets/{dataset_id}")
def dataset(dataset_id: str) -> dict[str, Any]:
    try:
        return catalog.get(dataset_id).model_dump(mode="json")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset not found") from exc


@router.post("/replay")
def replay(request: ReplayRequest) -> dict[str, Any]:
    try:
        events = catalog.read(request.dataset_id)
        strategy = make_strategy(request.strategy, request.parameters)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result = DeterministicReplayEngine(request.timer_interval_ms).run(events, strategy, request.starting_cash)
    return result.model_dump(mode="json")


@router.post("/experiments", status_code=202)
def create_experiment(config: ExperimentConfig) -> dict[str, Any]:
    try:
        record = experiment_store().create(config)
        job_id = enqueue_experiment(record.id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Experiment queue unavailable: {exc}") from exc
    payload = record.model_dump(mode="json")
    payload["job_id"] = job_id
    return payload


@router.get("/experiments/{experiment_id}")
def get_experiment(experiment_id: str) -> dict[str, Any]:
    try:
        return experiment_store().get(experiment_id).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Experiment not found") from exc


@router.get("/execution/safety")
def execution_safety() -> dict[str, Any]:
    return TestnetSafetyGate().status()


@router.post("/execution/testnet-order")
def testnet_order(
    request: TestnetOrderRequest,
    x_quantforge_safety_token: str | None = Header(default=None),
) -> dict[str, Any]:
    try:
        return HyperliquidTestnetAdapter().submit(request, x_quantforge_safety_token)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Testnet adapter failed: {exc}") from exc
