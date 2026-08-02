import time

from fastapi.testclient import TestClient

from app.main import app
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
