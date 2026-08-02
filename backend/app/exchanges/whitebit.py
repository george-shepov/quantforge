from __future__ import annotations

from datetime import datetime, timezone
import re

import httpx

from app.exchanges.base import ExchangeAdapter, ExchangeAdapterError
from app.exchanges.environment import configured_environment, endpoints_for
from app.models import Candle, MarketDataRequest


class WhiteBITAdapter(ExchangeAdapter):
    name = "whitebit"
    interval_map = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}

    async def fetch_candles(self, request: MarketDataRequest) -> list[Candle]:
        environment = configured_environment(self.name)
        endpoint = endpoints_for(self.name, environment)
        try:
            interval = self.interval_map[request.interval]
        except KeyError as exc:
            raise ExchangeAdapterError(f"WhiteBIT interval is not supported: {request.interval}") from exc

        params: dict[str, str | int] = {
            "market": _normalize_symbol(request.symbol, environment.value == "demo"),
            "interval": interval,
            "limit": min(request.limit, 1440),
        }
        if request.start_time:
            params["start"] = int(request.start_time.timestamp())
        if request.end_time:
            params["end"] = int(request.end_time.timestamp())

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(f"{endpoint.rest}/public/kline", params=params)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ExchangeAdapterError(f"WhiteBIT market-data request failed: {exc}") from exc

        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict):
            rows = payload.get("result", payload.get("data", []))
        else:
            rows = []
        candles: list[Candle] = []
        try:
            for row in rows or []:
                if isinstance(row, dict):
                    timestamp = row.get("time") or row.get("timestamp")
                    values = (row["open"], row["high"], row["low"], row["close"], row.get("volume", 0))
                else:
                    timestamp = row[0]
                    # WhiteBIT arrays are [time, open, close, high, low, volume].
                    values = (row[1], row[3], row[4], row[2], row[5] if len(row) > 5 else 0)
                timestamp_value = float(timestamp)
                if timestamp_value > 100_000_000_000:
                    timestamp_value /= 1000
                candles.append(
                    Candle(
                        timestamp=datetime.fromtimestamp(timestamp_value, tz=timezone.utc),
                        open=float(values[0]), high=float(values[1]), low=float(values[2]),
                        close=float(values[3]), volume=float(values[4]),
                    )
                )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ExchangeAdapterError("Unexpected WhiteBIT candle response") from exc
        candles.sort(key=lambda candle: candle.timestamp)
        if len(candles) < 20:
            raise ExchangeAdapterError("WhiteBIT returned too few candles")
        return candles[-request.limit :]

    async def fetch_order_book(self, symbol: str, depth: int = 50) -> dict:
        environment = configured_environment(self.name)
        endpoint = endpoints_for(self.name, environment)
        params = {"market": _normalize_symbol(symbol, environment.value == "demo"), "limit": min(depth, 100)}
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(f"{endpoint.rest}/public/orderbook", params=params)
            response.raise_for_status()
            payload = response.json()
        return {
            "exchange": self.name,
            "symbol": symbol.upper(),
            "timestamp_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
            "sequence": int(payload.get("timestamp", 0)) if isinstance(payload, dict) else 0,
            "bids": [[float(p), float(q)] for p, q in payload.get("bids", [])],
            "asks": [[float(p), float(q)] for p, q in payload.get("asks", [])],
            "environment": environment.value,
        }


def _normalize_symbol(symbol: str, demo: bool = False) -> str:
    parts = [part for part in re.split(r"[/_:\-]", symbol.upper()) if part and part not in {"PERP", "PERPETUAL"}]
    compact = parts[0] if len(parts) == 1 else ""
    if compact.endswith(("USDT", "USDC")):
        base = f"{compact[:-4]}_{compact[-4:]}"
    else:
        base = "_".join(parts[:2]) if len(parts) > 1 else f"{compact or symbol.upper()}_USDT"
    if len(parts) > 1 and parts[1] not in {"USDT", "USDC", "BTC", "EUR"}:
        base = f"{parts[0]}_USDT"
    if demo:
        left, right = base.split("_", 1)
        left = left if left.startswith("D") else f"D{left}"
        right = right if right.startswith("D") else f"D{right}"
        return f"{left}_{right}"
    return base
