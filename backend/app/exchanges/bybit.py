from __future__ import annotations

from datetime import datetime, timezone
import re

import httpx

from app.symbols import canonical_symbol

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

        payload = await _get_public_json(
            f"{endpoint.rest}/v5/market/kline",
            params,
            operation="market-data",
        )

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
        venue_symbol = _normalize_symbol(symbol)
        params = {"category": "linear", "symbol": venue_symbol, "limit": min(depth, 200)}
        payload = await _get_public_json(
            f"{endpoint.rest}/v5/market/orderbook",
            params,
            operation="order-book",
        )
        if payload.get("retCode") != 0:
            raise ExchangeAdapterError(payload.get("retMsg", "Bybit order-book request failed"))
        result = payload["result"]
        return {
            "exchange": self.name,
            "symbol": canonical_symbol(venue_symbol),
            "canonical_symbol": canonical_symbol(venue_symbol),
            "venue_symbol": venue_symbol,
            "timestamp_ms": int(result.get("ts", payload.get("time", 0))),
            "sequence": int(result.get("u", 0)),
            "bids": [[float(p), float(q)] for p, q in result.get("b", [])],
            "asks": [[float(p), float(q)] for p, q in result.get("a", [])],
            "environment": environment.value,
        }


async def _get_public_json(url: str, params: dict[str, str | int], *, operation: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 403:
            raise ExchangeAdapterError(
                f"Bybit {operation} request was blocked with HTTP 403. "
                "Bybit documents possible causes including restricted regions (such as US IP addresses), "
                "IP rate limiting, or a malformed GET request. Use synthetic fallback here and verify "
                "the server region plus request and rate-limit telemetry."
            ) from exc
        raise ExchangeAdapterError(f"Bybit {operation} request failed: {exc}") from exc
    except httpx.HTTPError as exc:
        raise ExchangeAdapterError(f"Bybit {operation} request failed: {exc}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise ExchangeAdapterError(
            f"Bybit {operation} returned a non-JSON response; inspect the response path and server region."
        ) from exc
    if not isinstance(payload, dict):
        raise ExchangeAdapterError(f"Unexpected Bybit {operation} response")
    return payload


def _normalize_symbol(symbol: str) -> str:
    parts = [part for part in re.split(r"[/_:\-]", symbol.upper()) if part and part not in {"PERP", "PERPETUAL"}]
    if len(parts) > 1:
        base, quote = parts[0], next((part for part in parts[1:] if part in {"USDT", "USDC"}), "USDT")
        return f"{base}{quote}"
    value = parts[0] if parts else symbol.upper()
    return value if value.endswith(("USDT", "USDC")) else f"{value}USDT"
