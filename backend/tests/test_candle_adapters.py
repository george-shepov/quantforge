import asyncio
from datetime import datetime, timezone

import httpx
import pytest

from app.exchanges.base import ExchangeAdapterError
from app.exchanges.bybit import BybitAdapter, _normalize_symbol as normalize_bybit
from app.exchanges.bitmex import _normalize_symbol as normalize_bitmex
from app.exchanges.hyperliquid import _interval_delta, _normalize_symbol as normalize_hyperliquid
from app.exchanges.whitebit import WhiteBITAdapter, _normalize_symbol as normalize_whitebit
from app.models import ExchangeName, MarketDataRequest


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://api.bybit.com/v5/market/kline")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("blocked", request=request, response=response)
        return None

    def json(self):
        return self.payload


class FakeClient:
    response = None
    request = None

    def __init__(self, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def get(self, url, params):
        self.request = (url, params)
        FakeClient.request = self.request
        return FakeClient.response


def request(exchange: ExchangeName) -> MarketDataRequest:
    return MarketDataRequest(exchange=exchange, symbol="BTC/USDT-PERP", interval="1h", limit=100)


def test_symbol_normalization_handles_common_perpetual_forms():
    assert normalize_bybit("BTC/USDT-PERP") == "BTCUSDT"
    assert normalize_bybit("BTCUSDT") == "BTCUSDT"
    assert normalize_hyperliquid("BTC/USDT-PERP") == "BTC"
    assert normalize_bitmex("BTC/USDT-PERP") == "XBTUSD"
    assert normalize_whitebit("BTC/USDT-PERP") == "BTC_USDT"
    assert normalize_whitebit("BTCUSDT", demo=True) == "DBTC_DUSDT"


def test_hyperliquid_weekly_window_uses_weeks():
    assert _interval_delta("1w", 3).days == 21


def test_order_book_adapters_separate_canonical_and_venue_symbols(monkeypatch):
    FakeClient.response = FakeResponse(
        {
            "retCode": 0,
            "result": {"ts": "1700000000000", "u": "9", "b": [["99", "1"]], "a": [["100", "1"]]},
        }
    )
    monkeypatch.setattr("app.exchanges.bybit.httpx.AsyncClient", FakeClient)
    bybit = asyncio.run(BybitAdapter().fetch_order_book("BTC/USDT-PERP"))

    FakeClient.response = FakeResponse(
        {"timestamp": 9, "bids": [["99", "1"]], "asks": [["100", "1"]]}
    )
    monkeypatch.setattr("app.exchanges.whitebit.httpx.AsyncClient", FakeClient)
    whitebit = asyncio.run(WhiteBITAdapter().fetch_order_book("BTC/USDT-PERP"))

    assert (bybit["symbol"], bybit["venue_symbol"]) == ("BTC", "BTCUSDT")
    assert (whitebit["symbol"], whitebit["venue_symbol"]) == ("BTC", "BTC_USDT")


def test_bybit_candles_are_reversed_to_chronological_order(monkeypatch):
    rows = [[str(1_700_000_000_000 + index * 3_600_000), "1", "3", "0", "2", "4"] for index in range(100)]
    FakeClient.response = FakeResponse({"retCode": 0, "result": {"list": list(reversed(rows))}})
    monkeypatch.setattr("app.exchanges.bybit.httpx.AsyncClient", FakeClient)

    candles = asyncio.run(BybitAdapter().fetch_candles(request(ExchangeName.BYBIT)))

    assert candles[0].open == 1
    assert candles[-1].timestamp > candles[0].timestamp
    assert FakeClient.request[1]["symbol"] == "BTCUSDT"
    assert FakeClient.request[1]["interval"] == "60"


def test_whitebit_candles_map_documented_array_order(monkeypatch):
    rows = [[1_700_000_000 + index * 3_600, "1", "2", "3", "0", "4"] for index in range(100)]
    FakeClient.response = FakeResponse({"success": True, "message": None, "result": list(reversed(rows))})
    monkeypatch.setattr("app.exchanges.whitebit.httpx.AsyncClient", FakeClient)

    candles = asyncio.run(WhiteBITAdapter().fetch_candles(request(ExchangeName.WHITEBIT)))

    assert candles[0].open == 1
    assert candles[0].close == 2
    assert candles[0].high == 3
    assert candles[0].low == 0
    assert candles[-1].timestamp == datetime.fromtimestamp(1_700_000_000 + 99 * 3_600, tz=timezone.utc)
    assert FakeClient.request[0] == "https://whitebit.com/api/v1/public/kline"
    assert FakeClient.request[1]["market"] == "BTC_USDT"
    assert FakeClient.request[1]["interval"] == "1h"


def test_bybit_403_lists_documented_possible_causes(monkeypatch):
    FakeClient.response = FakeResponse({}, status_code=403)
    monkeypatch.setattr("app.exchanges.bybit.httpx.AsyncClient", FakeClient)

    with pytest.raises(ExchangeAdapterError, match="IP rate limiting"):
        asyncio.run(BybitAdapter().fetch_candles(request(ExchangeName.BYBIT)))
