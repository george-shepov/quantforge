from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import numpy as np

from app.exchanges.base import ExchangeAdapter
from app.models import Candle, MarketDataRequest


class SyntheticAdapter(ExchangeAdapter):
    name = "synthetic"

    async def fetch_candles(self, request: MarketDataRequest) -> list[Candle]:
        count = request.limit
        seed_material = f"{request.symbol}:{request.interval}:{count}".encode()
        seed = int(hashlib.sha256(seed_material).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)
        start_price = _start_price(request.symbol)
        step = _interval_delta(request.interval)
        end = request.end_time or datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        start = request.start_time or end - step * (count - 1)

        # Regime-switching synthetic series: trend, chop, selloff, recovery.
        returns = rng.normal(0.00015, 0.012, count)
        quarters = np.array_split(np.arange(count), 4)
        returns[quarters[0]] += 0.00045
        returns[quarters[1]] -= 0.00010
        returns[quarters[2]] -= 0.00055
        returns[quarters[3]] += 0.00035

        closes = start_price * np.exp(np.cumsum(returns))
        opens = np.concatenate(([start_price], closes[:-1]))
        intrabar = np.maximum(np.abs(rng.normal(0.006, 0.004, count)), 0.001)
        highs = np.maximum(opens, closes) * (1 + intrabar)
        lows = np.minimum(opens, closes) * (1 - intrabar)
        volumes = rng.lognormal(mean=9.0, sigma=0.75, size=count)

        return [
            Candle(
                timestamp=start + step * i,
                open=float(opens[i]),
                high=float(highs[i]),
                low=float(max(lows[i], 0.000001)),
                close=float(closes[i]),
                volume=float(volumes[i]),
            )
            for i in range(count)
        ]


def _start_price(symbol: str) -> float:
    return {"BTC": 65_000.0, "XBT": 65_000.0, "ETH": 3_200.0, "SOL": 150.0, "HYPE": 40.0}.get(
        symbol.upper(), 100.0
    )


def _interval_delta(interval: str) -> timedelta:
    try:
        amount = int(interval[:-1])
    except ValueError:
        amount = 1
    if interval.endswith("m"):
        return timedelta(minutes=amount)
    if interval.endswith("d"):
        return timedelta(days=amount)
    return timedelta(hours=amount)
