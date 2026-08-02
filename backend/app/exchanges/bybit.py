from __future__ import annotations

from datetime import datetime, timezone
import re

import httpx

from app.exchanges.base import ExchangeAdapter, ExchangeAdapterError
from app.exchanges.environment import configured_environment, endpoints_for
from app.models import Candle, MarketDataRequest


class BybitAdapter(ExchangeAdapter):
    name = "bybit"
    interval_map = {"1m": "1", "5m": "5", "15m": "15", "1h": "60", "4h": "240", "1d": "D"}

    async def fetch_candles(self, request: MarketDataRequest) -> list[Candle]:
        environment = configured_environment(self.name)
        endpoint = endpoints_for(self.name, environment)
        try:
            interval = self.interval_map[request.interval]
        except KeyError as exc:
            raise ExchangeAdapterError(f"Bybit interval is not supported: {request.interval}") from exc

        params: dict[str, str | int] = {
            "category": "linear",
            "symbol": _normalize_symbol(request.symbol),
            "interval": interval,
            "limit": min(request.limit, 1000),
        }
        if request.start_time:
            params["start"] = int(request.start_time.timestamp() * 1000)
        if request.end_time:
            params["end"] = int(request.end_time.timestamp() * 1000)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(f"{endpoint.rest}/v5/market/kline", params=params)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ExchangeAdapterError(f"Bybit market-data request failed: {exc}") from exc

        if payload.get("retCode") != 0:
            raise ExchangeAdapterError(f"Bybit rejected market-data request: {payload.get('retMsg', 'unknown error')}")

        try:
            rows = payload["result"]["list"]
            candles = [
                Candle(
                    timestamp=datetime.fromtimestamp(float(row[0]) / 1000, tz=timezone.utc),
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                )
                for row in reversed(rows)
            ]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ExchangeAdapterError("Unexpected Bybit candle response") from exc
        if len(candles) < 20:
            raise ExchangeAdapterError("Bybit returned too few candles")
        return candles[-request.limit :]

    async def fetch_order_book(self, symbol: str, depth: int = 50) -> dict:
        environment = configured_environment(self.name)
        endpoint = endpoints_for(self.name, environment)
        params = {"category": "linear", "symbol": _normalize_symbol(symbol), "limit": min(depth, 200)}
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(f"{endpoint.rest}/v5/market/orderbook", params=params)
            response.raise_for_status()
            payload = response.json()
        if payload.get("retCode") != 0:
            raise ExchangeAdapterError(payload.get("retMsg", "Bybit order-book request failed"))
        result = payload["result"]
        return {
            "exchange": self.name,
            "symbol": symbol.upper(),
            "timestamp_ms": int(result.get("ts", payload.get("time", 0))),
            "sequence": int(result.get("u", 0)),
            "bids": [[float(p), float(q)] for p, q in result.get("b", [])],
            "asks": [[float(p), float(q)] for p, q in result.get("a", [])],
            "environment": environment.value,
        }


def _normalize_symbol(symbol: str) -> str:
    parts = [part for part in re.split(r"[/_:\-]", symbol.upper()) if part and part not in {"PERP", "PERPETUAL"}]
    if len(parts) > 1:
        base, quote = parts[0], next((part for part in parts[1:] if part in {"USDT", "USDC"}), "USDT")
        return f"{base}{quote}"
    value = parts[0] if parts else symbol.upper()
    return value if value.endswith(("USDT", "USDC")) else f"{value}USDT"
