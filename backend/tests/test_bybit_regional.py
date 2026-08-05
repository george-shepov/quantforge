from __future__ import annotations

import asyncio

import pytest

from app.exchanges.base import ExchangeAdapterError
from app.exchanges.bybit import BybitAdapter, BybitHttpError, RegionalConnectorError
from app.models import ExchangeName, MarketDataRequest


def request() -> MarketDataRequest:
    return MarketDataRequest(exchange=ExchangeName.BYBIT, symbol="BTCUSDT", interval="1h", limit=100)


def payload() -> dict:
    rows = [[str(1_700_000_000_000 + index * 3_600_000), "1", "3", "0", "2", "4"] for index in range(100)]
    return {"retCode": 0, "result": {"list": list(reversed(rows))}}


def test_regional_success_is_preferred(monkeypatch):
    monkeypatch.setenv("BYBIT_REGIONAL_CONNECTOR_PREFER", "true")
    calls = []

    async def regional(params):
        calls.append("regional")
        return payload()

    async def direct(*_args, **_kwargs):
        calls.append("direct")
        raise AssertionError("direct path should not be used when regional is healthy")

    monkeypatch.setattr("app.exchanges.bybit._get_regional_json", regional)
    monkeypatch.setattr("app.exchanges.bybit._get_public_json", direct)
    candles = asyncio.run(BybitAdapter().fetch_candles(request()))
    assert len(candles) == 100
    assert calls == ["regional"]


def test_direct_403_then_london_success(monkeypatch):
    monkeypatch.setenv("BYBIT_REGIONAL_CONNECTOR_PREFER", "false")
    calls = []

    async def direct(*_args, **_kwargs):
        calls.append("direct")
        raise BybitHttpError("market-data", 403)

    async def regional(_params):
        calls.append("regional")
        return payload()

    monkeypatch.setattr("app.exchanges.bybit._get_public_json", direct)
    monkeypatch.setattr("app.exchanges.bybit._get_regional_json", regional)
    candles = asyncio.run(BybitAdapter().fetch_candles(request()))
    assert len(candles) == 100
    assert calls == ["direct", "regional"]


def test_both_paths_fail_with_sanitized_diagnostics(monkeypatch):
    monkeypatch.setenv("BYBIT_REGIONAL_CONNECTOR_PREFER", "false")

    async def direct(*_args, **_kwargs):
        raise BybitHttpError("market-data", 403)

    async def regional(_params):
        raise RegionalConnectorError("regional connector HTTP 502")

    monkeypatch.setattr("app.exchanges.bybit._get_public_json", direct)
    monkeypatch.setattr("app.exchanges.bybit._get_regional_json", regional)
    with pytest.raises(ExchangeAdapterError, match=r"direct=HTTP 403; regional=regional connector HTTP 502"):
        asyncio.run(BybitAdapter().fetch_candles(request()))


def test_bybit_execution_remains_disabled():
    from app.exchanges.environment import ExchangeEnvironment, endpoints_for

    assert endpoints_for("bybit", ExchangeEnvironment.TESTNET).execution_allowed is False
    assert endpoints_for("bybit", ExchangeEnvironment.MAINNET_READONLY).execution_allowed is False
