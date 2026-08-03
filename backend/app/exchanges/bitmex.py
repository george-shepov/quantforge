from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

import httpx

from app.exchanges.base import ExchangeAdapter, ExchangeAdapterError
from app.exchanges.environment import configured_environment, endpoints_for
from app.models import Candle, MarketDataRequest


class BitMEXAdapter(ExchangeAdapter):
    name = "bitmex"

    async def fetch_candles(self, request: MarketDataRequest) -> list[Candle]:
        environment = configured_environment(self.name)
        endpoint = endpoints_for(self.name, environment)
        native_interval, aggregate_factor = _resolve_interval(request.interval)
        end = request.end_time or datetime.now(timezone.utc)
        start = request.start_time or end - _interval_delta(request.interval, request.limit)
        params = {
            "binSize": native_interval,
            "partial": "false",
            "symbol": _normalize_symbol(request.symbol),
            "count": min(request.limit * aggregate_factor, 1000),
            "reverse": "false",
            "startTime": start.isoformat(),
            "endTime": end.isoformat(),
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(f"{endpoint.rest}/trade/bucketed", params=params)
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ExchangeAdapterError(f"BitMEX market-data request failed: {exc}") from exc

        try:
            candles = [
                Candle(
                    timestamp=datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")),
                    open=float(row["open"]), high=float(row["high"]), low=float(row["low"]),
                    close=float(row["close"]), volume=float(row.get("volume") or 0.0),
                )
                for row in data if row.get("open") is not None
            ]
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise ExchangeAdapterError("Unexpected BitMEX candle response") from exc
        if aggregate_factor > 1:
            candles = _aggregate(candles, aggregate_factor)
        candles = candles[-request.limit :]
        if len(candles) < 20:
            raise ExchangeAdapterError("BitMEX returned too few candles")
        return candles


def _resolve_interval(interval: str) -> tuple[str, int]:
    if interval in {"1m", "5m", "1h", "1d"}:
        return interval, 1
    if interval == "15m":
        return "5m", 3
    if interval == "4h":
        return "1h", 4
    raise ExchangeAdapterError(f"BitMEX interval is not supported: {interval}")


def _aggregate(candles: list[Candle], factor: int) -> list[Candle]:
    aggregated: list[Candle] = []
    for start in range(0, len(candles), factor):
        group = candles[start : start + factor]
        if len(group) < factor:
            continue
        aggregated.append(Candle(timestamp=group[-1].timestamp, open=group[0].open,
            high=max(c.high for c in group), low=min(c.low for c in group),
            close=group[-1].close, volume=sum(c.volume for c in group)))
    return aggregated


def _normalize_symbol(symbol: str) -> str:
    parts = [
        part
        for part in re.split(r"[/_:\-]", symbol.upper())
        if part and part not in {"PERP", "PERPETUAL"}
    ]
    if not parts:
        raise ExchangeAdapterError("BitMEX symbol is empty")
    value = parts[0]
    if value in {"BTC", "XBT", "BTCUSD", "BTCUSDT", "BTCUSDC"}:
        return "XBTUSD"
    if value in {"ETH", "ETHUSD", "ETHUSDT", "ETHUSDC"}:
        return "ETHUSD"
    return value


def _interval_delta(interval: str, bars: int) -> timedelta:
    if interval.endswith("m"):
        return timedelta(minutes=int(interval[:-1]) * bars)
    if interval.endswith("h"):
        return timedelta(hours=int(interval[:-1]) * bars)
    return timedelta(days=int(interval[:-1]) * bars)
