import time

from fastapi.testclient import TestClient

from app.main import app
from app.research import api as research_api
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
