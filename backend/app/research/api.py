from __future__ import annotations

import os
from dataclasses import asdict
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from .engine import DeterministicReplayEngine, make_strategy, scan_arbitrage_events
from .events import EventDatasetCatalog, RecorderConfig, RecorderManager
from .execution import HyperliquidTestnetAdapter, TestnetOrderRequest, TestnetSafetyGate
from .execution_story import StoryMode, build_execution_story
from .orderbook import OrderBookSnapshot, Side, simulate_order
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


class ArbitrageScanRequest(BaseModel):
    dataset_id: str
    min_edge_bps: float = Field(default=5.0, ge=-10_000, le=10_000)
    fee_bps: float = Field(default=2.0, ge=0, le=1_000)
    max_quantity: float = Field(default=1.0, gt=0)
    limit: int = Field(default=500, ge=1, le=5_000)


class ExecutionStoryRequest(BaseModel):
    snapshot: dict[str, Any]
    side: str = "buy"
    quantity: float = Field(gt=0)
    limit_price: float | None = None
    mode: StoryMode = StoryMode.GUIDED
    intent: str = "Understand how the recorded order book would execute this order."
    hypothesis: str = "The order should execute near the best displayed price."
    assumptions: list[str] = Field(default_factory=list)
    invalidation_conditions: list[str] = Field(default_factory=list)
    hopes: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


@router.get("/capabilities")
def capabilities() -> dict[str, Any]:
    return {
        "market_data": ["hyperliquid_l2_book", "hyperliquid_trades", "hyperliquid_all_mids", "hyperliquid_funding"],
        "datasets": ["partitioned_parquet", "manifest_catalog", "checksum_chain", "deterministic_replay"],
        "strategy_callbacks": ["on_book", "on_trade", "on_funding", "on_timer"],
        "portfolio": ["multi_asset", "multi_exchange", "cross_exchange_arbitrage"],
        "research": ["arbitrage_decision_projection", "parameter_sweeps", "walk_forward", "block_monte_carlo"],
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


@router.post("/arbitrage/scan")
def scan_arbitrage(request: ArbitrageScanRequest) -> dict[str, Any]:
    try:
        events = catalog.read(request.dataset_id)
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return scan_arbitrage_events(
        events,
        dataset_id=request.dataset_id,
        min_edge_bps=request.min_edge_bps,
        fee_bps=request.fee_bps,
        max_quantity=request.max_quantity,
        limit=request.limit,
    )


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


@router.get("/experiments")
def list_experiments(limit: int = Query(default=25, ge=1, le=100)) -> list[dict[str, Any]]:
    try:
        return [record.model_dump(mode="json") for record in experiment_store().list_recent(limit)]
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Experiment store unavailable: {exc}") from exc


@router.get("/experiments/{experiment_id}")
def get_experiment(experiment_id: str) -> dict[str, Any]:
    try:
        return experiment_store().get(experiment_id).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Experiment not found") from exc


@router.get("/execution/safety")
def execution_safety() -> dict[str, Any]:
    return TestnetSafetyGate().status()


@router.post("/execution/story")
def execution_story(request: ExecutionStoryRequest) -> dict[str, Any]:
    try:
        snapshot = OrderBookSnapshot.from_payload(request.snapshot)
        side = Side(request.side)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid execution story request: {exc}") from exc

    result = simulate_order(snapshot, side, request.quantity, request.limit_price)
    story = build_execution_story(
        snapshot,
        side,
        result,
        intent=request.intent,
        hypothesis=request.hypothesis,
        assumptions=request.assumptions,
        invalidation_conditions=request.invalidation_conditions,
        hopes=request.hopes,
        risks=request.risks,
    )
    return {
        "execution": {
            "requested_quantity": result.requested_quantity,
            "filled_quantity": result.filled_quantity,
            "remaining_quantity": result.remaining_quantity,
            "average_price": result.average_price,
            "status": result.status.value,
            "fills": [asdict(fill) for fill in result.fills],
        },
        "story": story.render(request.mode),
    }


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
