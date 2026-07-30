from __future__ import annotations

import numpy as np

from app.models import Candle, ScenarioConfig, ScenarioName


def apply_scenario(candles: list[Candle], config: ScenarioConfig) -> tuple[list[Candle], float, float]:
    if config.name == ScenarioName.BASELINE:
        return candles, 1.0, config.funding_rate_hourly

    result = [c.model_copy(deep=True) for c in candles]
    start = min(max(int(len(result) * config.start_percent), 1), len(result) - 1)
    end = min(start + config.duration_bars, len(result))
    slippage_multiplier = 1.0
    funding = config.funding_rate_hourly

    if config.name == ScenarioName.FLASH_CRASH:
        shock = 1.0 + config.shock_pct
        recovery = np.linspace(shock, 1.0, max(end - start, 2))
        anchor = result[start - 1].close
        for offset, i in enumerate(range(start, end)):
            multiplier = float(recovery[min(offset, len(recovery) - 1)])
            c = result[i]
            c.open *= multiplier
            c.close *= multiplier
            c.high = max(c.open, c.close, c.high * multiplier)
            c.low = min(c.open, c.close, anchor * shock * 0.985, c.low * multiplier)
    elif config.name == ScenarioName.VOLATILITY_SPIKE:
        for i in range(start, end):
            c = result[i]
            midpoint = (c.open + c.close) / 2
            c.open = midpoint + (c.open - midpoint) * config.volatility_multiplier
            c.close = midpoint + (c.close - midpoint) * config.volatility_multiplier
            c.high = max(c.open, c.close) * (1 + 0.01 * config.volatility_multiplier)
            c.low = max(0.000001, min(c.open, c.close) * (1 - 0.01 * config.volatility_multiplier))
    elif config.name == ScenarioName.LIQUIDITY_DROUGHT:
        slippage_multiplier = config.slippage_multiplier
        for i in range(start, end):
            result[i].volume /= config.slippage_multiplier
    elif config.name == ScenarioName.FUNDING_SQUEEZE:
        funding = abs(config.funding_rate_hourly) * config.volatility_multiplier

    return result, slippage_multiplier, funding
