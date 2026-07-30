from __future__ import annotations

import numpy as np

from app.engine.indicators import ema, rolling_high, rolling_low, rolling_zscore
from app.models import MarketKind, StrategyConfig, StrategyName


def build_signals(closes: np.ndarray, config: StrategyConfig, market_kind: MarketKind) -> np.ndarray:
    if config.name == StrategyName.EMA_CROSSOVER:
        fast = ema(closes, config.fast_period)
        slow = ema(closes, config.slow_period)
        signals = np.where(fast > slow, 1, -1)
        signals[: config.slow_period] = 0
    elif config.name == StrategyName.MEAN_REVERSION:
        z = rolling_zscore(closes, config.lookback)
        signals = _stateful_mean_reversion(z, config.entry_z, config.exit_z)
    elif config.name == StrategyName.BREAKOUT:
        high = rolling_high(closes, config.breakout_period)
        low = rolling_low(closes, config.breakout_period)
        signals = np.zeros(len(closes), dtype=int)
        state = 0
        for i in range(config.breakout_period, len(closes)):
            if closes[i] > high[i]:
                state = 1
            elif closes[i] < low[i]:
                state = -1
            signals[i] = state
    else:
        raise ValueError(f"Unsupported strategy: {config.name}")

    if market_kind == MarketKind.SPOT:
        signals = np.where(signals > 0, 1, 0)
    return signals.astype(int)


def _stateful_mean_reversion(z: np.ndarray, entry_z: float, exit_z: float) -> np.ndarray:
    signals = np.zeros(len(z), dtype=int)
    state = 0
    for i, value in enumerate(z):
        if state == 0:
            if value <= -entry_z:
                state = 1
            elif value >= entry_z:
                state = -1
        elif state == 1 and value >= -exit_z:
            state = 0
        elif state == -1 and value <= exit_z:
            state = 0
        signals[i] = state
    return signals
