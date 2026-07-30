from __future__ import annotations

import math
from datetime import datetime

import numpy as np

from app.models import BacktestMetrics, EquityPoint, TradeRecord


def calculate_metrics(
    starting_capital: float,
    equity_curve: list[EquityPoint],
    trades: list[TradeRecord],
    bars_in_position: int,
    liquidation_count: int,
) -> BacktestMetrics:
    ending = equity_curve[-1].equity if equity_curve else starting_capital
    equities = np.array([p.equity for p in equity_curve], dtype=float)
    returns = np.diff(equities) / np.maximum(equities[:-1], 1e-12) if len(equities) > 1 else np.array([])
    periods_per_year = _periods_per_year(equity_curve)

    total_return = ending / starting_capital - 1
    years = max(_years_between(equity_curve), 1 / periods_per_year)
    annualized_return = (max(ending, 1e-9) / starting_capital) ** (1 / years) - 1 if ending > 0 else -1
    volatility = float(np.std(returns, ddof=1) * math.sqrt(periods_per_year)) if len(returns) > 1 else 0.0
    mean_return = float(np.mean(returns)) if len(returns) else 0.0
    return_std = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.0
    downside = returns[returns < 0]
    downside_std = float(np.std(downside, ddof=1)) if len(downside) > 1 else 0.0
    sharpe = mean_return / return_std * math.sqrt(periods_per_year) if return_std > 0 else 0.0
    sortino = mean_return / downside_std * math.sqrt(periods_per_year) if downside_std > 0 else 0.0

    pnls = np.array([t.net_pnl for t in trades], dtype=float)
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    gross_wins = float(wins.sum()) if len(wins) else 0.0
    gross_losses = float(abs(losses.sum())) if len(losses) else 0.0

    return BacktestMetrics(
        starting_capital=round(starting_capital, 2),
        ending_equity=round(ending, 2),
        net_profit=round(ending - starting_capital, 2),
        total_return_pct=round(total_return * 100, 4),
        annualized_return_pct=round(annualized_return * 100, 4),
        annualized_volatility_pct=round(volatility * 100, 4),
        sharpe_ratio=round(sharpe, 4),
        sortino_ratio=round(sortino, 4),
        max_drawdown_pct=round(max((p.drawdown_pct for p in equity_curve), default=0.0), 4),
        win_rate_pct=round((len(wins) / len(pnls) * 100) if len(pnls) else 0.0, 4),
        average_gain=round(float(wins.mean()) if len(wins) else 0.0, 2),
        average_loss=round(float(losses.mean()) if len(losses) else 0.0, 2),
        profit_factor=round(gross_wins / gross_losses, 4) if gross_losses > 0 else (999.0 if gross_wins > 0 else 0.0),
        expectancy=round(float(pnls.mean()) if len(pnls) else 0.0, 2),
        exposure_pct=round((bars_in_position / len(equity_curve) * 100) if equity_curve else 0.0, 4),
        total_fees=round(sum(t.fees for t in trades), 2),
        total_funding=round(sum(t.funding for t in trades), 2),
        trade_count=len(trades),
        liquidation_count=liquidation_count,
    )


def _periods_per_year(points: list[EquityPoint]) -> float:
    if len(points) < 2:
        return 365.0
    seconds = (points[1].timestamp - points[0].timestamp).total_seconds()
    return max(365.0 * 24 * 3600 / max(seconds, 1), 1.0)


def _years_between(points: list[EquityPoint]) -> float:
    if len(points) < 2:
        return 0.0
    return max((points[-1].timestamp - points[0].timestamp).total_seconds() / (365.0 * 24 * 3600), 0.0)
