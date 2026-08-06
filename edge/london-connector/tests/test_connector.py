from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from pathlib import Path

import httpx
import pytest

from app.main import app
from app.store import ReplayStore


SECRET = "test-only-regional-secret-0123456789012345"


def _signature(method: str, path: str, body: bytes, timestamp: str, nonce: str) -> str:
    digest = hashlib.sha256(body).hexdigest()
    canonical = "\n".join((timestamp, nonce, method, path, digest)).encode()
    return hmac.new(SECRET.encode(), canonical, hashlib.sha256).hexdigest()


def _headers(method: str, path: str, body: bytes, nonce: str) -> dict[str, str]:
    timestamp = str(int(time.time()))
    return {
        "X-QuantForge-Timestamp": timestamp,
        "X-QuantForge-Nonce": nonce,
        "X-QuantForge-Signature": _signature(method, path, body, timestamp, nonce),
    }


@pytest.fixture(autouse=True)
def configure_auth(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("BYBIT_REGIONAL_CONNECTOR_SECRET", SECRET)
    app.state.replay_store = ReplayStore(tmp_path / "replay.sqlite3")


def test_health_and_authenticated_regional_success(monkeypatch: pytest.MonkeyPatch):
    async def run():
        async def fake_fetch(params):
            assert params == {"category": "linear", "symbol": "BTCUSDT", "interval": "60", "limit": 100}
            return 200, {"retCode": 0, "result": {"list": []}}

        monkeypatch.setattr("app.main.fetch_kline", fake_fetch)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            health = await client.get("/health")
            assert health.json() == {"status": "ok", "service": "quantforge-london-connector", "execution_enabled": False}
            body = json.dumps({"category": "linear", "symbol": "BTCUSDT", "interval": "60", "limit": 100}).encode()
            response = await client.post(
                "/v1/exchanges/bybit/kline",
                content=body,
                headers={**_headers("POST", "/v1/exchanges/bybit/kline", body, "nonce-success-123456"), "Content-Type": "application/json"},
            )
        assert response.status_code == 200
        assert response.json()["exchange_http_status"] == 200
        assert response.json()["node_id"] == "eu-london"

    asyncio.run(run())


def test_hmac_replay_and_validation(monkeypatch: pytest.MonkeyPatch):
    async def run():
        async def fake_fetch(params):
            return 200, {"retCode": 0}

        monkeypatch.setattr("app.main.fetch_kline", fake_fetch)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            body = json.dumps({"category": "spot", "symbol": "ETHUSDT", "interval": "1", "limit": 1}).encode()
            headers = {**_headers("POST", "/v1/exchanges/bybit/kline", body, "nonce-replay-123456"), "Content-Type": "application/json"}
            first = await client.post("/v1/exchanges/bybit/kline", content=body, headers=headers)
            replay = await client.post("/v1/exchanges/bybit/kline", content=body, headers=headers)
            invalid_body = json.dumps({"category": "spot", "symbol": "ethusdt", "interval": "1", "limit": 1}).encode()
            invalid = await client.post(
                "/v1/exchanges/bybit/kline",
                content=invalid_body,
                headers={**_headers("POST", "/v1/exchanges/bybit/kline", invalid_body, "nonce-invalid-123456"), "Content-Type": "application/json"},
            )
        assert first.status_code == 200
        assert replay.status_code == 409
        assert invalid.status_code == 422

    asyncio.run(run())


def test_auth_rejects_bad_signature():
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/v1/exchanges/bybit/kline",
                json={"category": "linear", "symbol": "BTCUSDT", "interval": "60", "limit": 1},
                headers={
                    "X-QuantForge-Timestamp": str(int(time.time())),
                    "X-QuantForge-Nonce": "nonce-bad-signature-123456",
                    "X-QuantForge-Signature": "0" * 64,
                },
            )

    assert asyncio.run(run()).status_code == 401


def test_only_fixed_bybit_kline_endpoint_is_defined():
    from app.bybit import BYBIT_KLINE_URL

    assert BYBIT_KLINE_URL == "https://api.bybit.com/v5/market/kline"
    assert "order" not in BYBIT_KLINE_URL
