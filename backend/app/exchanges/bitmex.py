from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from app.exchanges.base import ExchangeAdapter, ExchangeAdapterError
from app.models import Candle, MarketDataRequest


class BitMEXAdapter(ExchangeAdapter):
    name = "bitmex"
    base_url = "https://www.bitmex.com/api/v1/trade/bucketed"
    interval_map = {"1m": "1m", "5m": "5m", "1h": "1h", "1d": "1d"}

    async def fetch_candles(self, request: MarketDataRequest) -> list[Candle]:
        native_interval, aggregate_factor = _resolve_interval(request.interval)
        end = request.end_time or datetime.now(timezone.utc)
        start = request.start_time or end - _interval_delta(request.interval, request.limit)
        symbol = _normalize_symbol(request.symbol)
        params = {
            "binSize": native_interval,
            "partial": "false",
            "symbol": symbol,
            "count": min(request.limit * aggregate_factor, 1000),
            "reverse": "false",
            "startTime": start.isoformat(),
            "endTime": end.isoformat(),
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ExchangeAdapterError(f"BitMEX market-data request failed: {exc}") from exc

        candles: list[Candle] = []
        for row in data:
            if row.get("open") is None:
                continue
            candles.append(
                Candle(
                    timestamp=datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume") or 0.0),
                )
            )
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
        aggregated.append(
            Candle(
                timestamp=group[-1].timestamp,
                open=group[0].open,
                high=max(c.high for c in group),
                low=min(c.low for c in group),
                close=group[-1].close,
                volume=sum(c.volume for c in group),
            )
        )
    return aggregated


def _normalize_symbol(symbol: str) -> str:
    value = symbol.upper().replace("-PERP", "")
    if value in {"BTC", "XBT"}:
        return "XBTUSD"
    if value == "ETH":
        return "ETHUSD"
    return value


def _interval_delta(interval: str, bars: int) -> timedelta:
    if interval.endswith("m"):
        return timedelta(minutes=int(interval[:-1]) * bars)
    if interval.endswith("h"):
        return timedelta(hours=int(interval[:-1]) * bars)
    return timedelta(days=int(interval[:-1]) * bars)
