from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

import httpx

from app.exchanges.base import ExchangeAdapter, ExchangeAdapterError
from app.exchanges.environment import configured_environment, endpoints_for
from app.models import Candle, MarketDataRequest


class HyperliquidAdapter(ExchangeAdapter):
    name = "hyperliquid"

    async def fetch_candles(self, request: MarketDataRequest) -> list[Candle]:
        environment = configured_environment(self.name)
        endpoint = endpoints_for(self.name, environment)
        end = request.end_time or datetime.now(timezone.utc)
        start = request.start_time or end - _interval_delta(request.interval, request.limit)
        payload = {
            "type": "candleSnapshot",
            "req": {
                "coin": _normalize_symbol(request.symbol),
                "interval": _normalize_interval(request.interval),
                "startTime": int(start.timestamp() * 1000),
                "endTime": int(end.timestamp() * 1000),
            },
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(f"{endpoint.rest}/info", json=payload)
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ExchangeAdapterError(f"Hyperliquid market-data request failed: {exc}") from exc

        candles: list[Candle] = []
        for row in data[-request.limit :]:
            try:
                candles.append(
                    Candle(
                        timestamp=datetime.fromtimestamp(float(row["t"]) / 1000, tz=timezone.utc),
                        open=float(row["o"]), high=float(row["h"]), low=float(row["l"]),
                        close=float(row["c"]), volume=float(row.get("v", 0.0)),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ExchangeAdapterError("Unexpected Hyperliquid candle response") from exc
        if len(candles) < 20:
            raise ExchangeAdapterError("Hyperliquid returned too few candles")
        return candles


def _normalize_symbol(symbol: str) -> str:
    parts = [
        part
        for part in re.split(r"[/_:\-]", symbol.upper())
        if part and part not in {"PERP", "PERPETUAL"}
    ]
    if not parts:
        raise ExchangeAdapterError("Hyperliquid symbol is empty")
    base = parts[0]
    if len(parts) == 1:
        for quote in ("USDT", "USDC"):
            if base.endswith(quote) and len(base) > len(quote):
                base = base[: -len(quote)]
                break
    return base


def _normalize_interval(interval: str) -> str:
    value = interval.strip().lower()
    if value not in {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "8h", "12h", "1d", "3d", "1w"}:
        raise ExchangeAdapterError(f"Hyperliquid interval is not supported: {interval}")
    return value


def _interval_delta(interval: str, bars: int) -> timedelta:
    units = {"m": "minutes", "h": "hours", "d": "days", "w": "weeks"}
    suffix = interval[-1]
    if suffix not in units:
        return timedelta(hours=bars)
    try:
        amount = int(interval[:-1])
    except ValueError:
        amount = 1
    return timedelta(**{units[suffix]: amount * bars})
