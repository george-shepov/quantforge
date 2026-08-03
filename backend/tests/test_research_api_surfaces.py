import time

import pytest
from fastapi.testclient import TestClient

from app import main as main_api
from app.exchanges.base import ExchangeAdapterError
from app.main import app
from app.research import api as research_api
from app.research import persistence as research_persistence
from app.research.events import EventKind, MarketEvent
from app.research.persistence import ExperimentConfig, ExperimentStore


client = TestClient(app)


def test_catalog_exposes_environment_badges():
    response = client.get("/api/catalog")
    assert response.status_code == 200
    payload = response.json()
    assert payload["mainnetOrderSubmission"] is False
    assert "hyperliquid" in payload["exchangeEnvironments"]
    assert "EXECUTION DISABLED" in payload["exchangeEnvironments"]["hyperliquid"]["badge"]


def test_blocked_live_exchange_falls_back_with_an_explicit_warning(monkeypatch):
    class RegionBlockedAdapter:
        name = "bybit"

        async def fetch_candles(self, request):
            raise ExchangeAdapterError(
                "Bybit market-data request was blocked with HTTP 403; verify region and rate-limit telemetry."
            )

    monkeypatch.setenv("QUANTFORGE_ALLOW_NETWORK", "true")
    monkeypatch.setattr(main_api, "get_exchange_adapter", lambda _exchange: RegionBlockedAdapter())
    response = client.post(
        "/api/backtests/run",
        json={"market": {"exchange": "bybit", "limit": 100}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "synthetic-fallback"
    assert payload["warnings"][0] == (
        "Bybit market-data request was blocked with HTTP 403; verify region and rate-limit telemetry."
    )
    assert "deterministic synthetic candles" in payload["warnings"][1]


def test_execution_story_endpoint_supports_guided_mode():
    response = client.post(
        "/api/research/execution/story",
        json={
            "snapshot": {
                "exchange": "bybit",
                "symbol": "BTC",
                "timestamp_ms": 1234,
                "sequence": 7,
                "environment": "simulation",
                "bids": [[99, 2]],
                "asks": [[100, 0.4], [101, 0.3]],
            },
            "side": "buy",
            "quantity": 1,
            "mode": "guided",
            "intent": "Validate available depth.",
            "hypothesis": "The order fills completely.",
            "assumptions": ["Snapshot is fresh"],
            "risks": ["Partial fill risk"],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["execution"]["status"] == "partially_filled"
    assert payload["execution"]["filled_quantity"] == 0.7
    assert payload["story"]["mode"] == "guided"
    assert payload["story"]["validationSteps"]


def test_experiment_store_lists_newest_first(tmp_path):
    store = ExperimentStore(f"sqlite:///{tmp_path / 'experiments.sqlite3'}")
    first = store.create(ExperimentConfig(dataset_id="first", strategy="cross_exchange_arbitrage"))
    time.sleep(0.002)
    second = store.create(ExperimentConfig(dataset_id="second", strategy="inventory_market_making"))

    recent = store.list_recent()

    assert [item.id for item in recent] == [second.id, first.id]


def test_arbitrage_scan_returns_accepted_and_rejected_explanations(monkeypatch):
    def book(sequence, exchange, bid, ask, bid_size=1, ask_size=1):
        return MarketEvent.build(
            sequence=sequence,
            exchange=exchange,
            symbol="BTC",
            kind=EventKind.BOOK,
            event_time_ns=sequence * 1_000_000,
            receive_time_ns=sequence * 1_000_000,
            payload={
                "levels": [
                    [{"px": str(bid), "sz": str(bid_size)}],
                    [{"px": str(ask), "sz": str(ask_size)}],
                ]
            },
        )

    events = [
        book(1, "hyperliquid", 99, 100, ask_size=0.6),
        book(2, "bybit", 100.20, 101, bid_size=0.4),
    ]

    class CatalogStub:
        def read(self, dataset_id):
            assert dataset_id == "lesson-31"
            return list(reversed(events))

    monkeypatch.setattr(research_api, "catalog", CatalogStub())
    response = client.post(
        "/api/research/arbitrage/scan",
        json={"dataset_id": "lesson-31", "min_edge_bps": 5, "fee_bps": 2, "max_quantity": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["strategy"] == "cross_exchange_arbitrage"
    assert payload["safety"]["order_submission"] is False
    assert payload["accepted_count"] == 1
    assert payload["rejected_count"] == 1
    accepted = next(item for item in payload["opportunities"] if item["decision"] == "accepted")
    rejected = next(item for item in payload["opportunities"] if item["decision"] == "rejected")
    assert accepted["buy_exchange"] == "hyperliquid"
    assert accepted["sell_exchange"] == "bybit"
    assert accepted["buy_source_event_checksum"] == events[0].checksum
    assert accepted["sell_source_event_checksum"] == events[1].checksum
    assert accepted["buy_timestamp_ns"] == events[0].event_time_ns
    assert accepted["sell_timestamp_ns"] == events[1].event_time_ns
    assert accepted["quantity"] == 0.4
    assert accepted["estimated_profit"] > 0
    assert rejected["rejection_reasons"]
    assert "Rejected because" in rejected["explanation"]

    repeated = client.post(
        "/api/research/arbitrage/scan",
        json={"dataset_id": "lesson-31", "min_edge_bps": 5, "fee_bps": 2, "max_quantity": 1},
    ).json()
    assert [item["opportunity_id"] for item in repeated["opportunities"]] == [
        item["opportunity_id"] for item in payload["opportunities"]
    ]


def test_replay_uses_the_scanner_fee_parameter(monkeypatch):
    def book(sequence, exchange, bid, ask):
        return MarketEvent.build(
            sequence=sequence,
            exchange=exchange,
            symbol="BTC",
            kind=EventKind.BOOK,
            event_time_ns=sequence * 1_000_000,
            receive_time_ns=sequence * 1_000_000,
            payload={
                "levels": [
                    [{"px": str(bid), "sz": "1"}],
                    [{"px": str(ask), "sz": "1"}],
                ]
            },
        )

    events = [book(1, "buy", 99, 100), book(2, "sell", 102, 103)]

    class CatalogStub:
        def read(self, dataset_id):
            assert dataset_id == "fee-check"
            return events

    monkeypatch.setattr(research_api, "catalog", CatalogStub())
    response = client.post(
        "/api/research/replay",
        json={
            "dataset_id": "fee-check",
            "strategy": "cross_exchange_arbitrage",
            "parameters": {"min_edge_bps": 5, "fee_bps": 7, "max_quantity": 1},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["fill_count"] == 2
    assert payload["portfolio"]["fees_paid"] == pytest.approx((100 + 102) * 7 / 10_000)


def test_experiment_grid_builds_each_replay_with_its_fee_parameter(monkeypatch):
    class CatalogStub:
        def read(self, dataset_id):
            assert dataset_id == "fee-grid"
            return [object(), object(), object(), object()]

    seen_fees: list[float] = []

    class ReplayStub:
        def __init__(self, timer_interval_ms, fee_bps):
            assert timer_interval_ms == 1_000
            seen_fees.append(fee_bps)

        def run(self, events, strategy, starting_cash):
            class Result:
                event_count = len(events)
                return_pct = 0.0
                max_drawdown_pct = 0.0
                fill_count = 0

            return Result()

    monkeypatch.setattr(research_persistence, "EventDatasetCatalog", lambda: CatalogStub())
    monkeypatch.setattr(research_persistence, "DeterministicReplayEngine", ReplayStub)

    result = research_persistence.run_experiment(
        ExperimentConfig(
            dataset_id="fee-grid",
            strategy="cross_exchange_arbitrage",
            base_parameters={"min_edge_bps": 5},
            parameter_grid={"fee_bps": [2, 7]},
            walk_forward_folds=1,
            monte_carlo_runs=0,
        )
    )

    assert seen_fees == [2.0, 7.0]
    assert {candidate["parameters"]["fee_bps"] for candidate in result["candidates"]} == {2, 7}
