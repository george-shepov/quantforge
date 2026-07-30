from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from app.exchanges.base import ExchangeAdapter, ExchangeAdapterError
from app.models import Candle, MarketDataRequest


class HyperliquidAdapter(ExchangeAdapter):
    name = "hyperliquid"
    base_url = "https://api.hyperliquid.xyz/info"

    async def fetch_candles(self, request: MarketDataRequest) -> list[Candle]:
        end = request.end_time or datetime.now(timezone.utc)
        start = request.start_time or end - _interval_delta(request.interval, request.limit)
        payload = {
            "type": "candleSnapshot",
            "req": {
                "coin": request.symbol.upper(),
                "interval": request.interval,
                "startTime": int(start.timestamp() * 1000),
                "endTime": int(end.timestamp() * 1000),
            },
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(self.base_url, json=payload)
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
                        open=float(row["o"]),
                        high=float(row["h"]),
                        low=float(row["l"]),
                        close=float(row["c"]),
                        volume=float(row.get("v", 0.0)),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ExchangeAdapterError("Unexpected Hyperliquid candle response") from exc
        if len(candles) < 20:
            raise ExchangeAdapterError("Hyperliquid returned too few candles")
        return candles


def _interval_delta(interval: str, bars: int) -> timedelta:
    units = {"m": "minutes", "h": "hours", "d": "days"}
    suffix = interval[-1]
    if suffix not in units:
        return timedelta(hours=bars)
    try:
        amount = int(interval[:-1])
    except ValueError:
        amount = 1
    return timedelta(**{units[suffix]: amount * bars})
