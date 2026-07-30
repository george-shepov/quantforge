from __future__ import annotations

import numpy as np
import pandas as pd


def ema(values: np.ndarray, period: int) -> np.ndarray:
    return pd.Series(values).ewm(span=period, adjust=False).mean().to_numpy()


def rolling_zscore(values: np.ndarray, period: int) -> np.ndarray:
    series = pd.Series(values)
    mean = series.rolling(period).mean()
    std = series.rolling(period).std(ddof=0).replace(0, np.nan)
    return ((series - mean) / std).fillna(0.0).to_numpy()


def rolling_high(values: np.ndarray, period: int) -> np.ndarray:
    return pd.Series(values).rolling(period).max().shift(1).to_numpy()


def rolling_low(values: np.ndarray, period: int) -> np.ndarray:
    return pd.Series(values).rolling(period).min().shift(1).to_numpy()
