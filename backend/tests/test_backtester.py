from __future__ import annotations

import asyncio

from app.engine import run_backtest
from app.exchanges.synthetic import SyntheticAdapter
from app.models import BacktestRequest, ExchangeName, MarketKind, ScenarioName, StrategyName


def test_backtest_returns_metrics_and_curve() -> None:
    request = BacktestRequest()
    request.market.exchange = ExchangeName.SYNTHETIC
    request.market.limit = 500
    candles = asyncio.run(SyntheticAdapter().fetch_candles(request.market))
    response = asyncio.run(run_backtest(request, candles, "synthetic", []))

    assert len(response.equity_curve) == 500
    assert response.metrics.starting_capital == 100_000
    assert response.metrics.trade_count >= 1
    assert response.metrics.ending_equity > 0


def test_spot_never_short_and_forces_one_x() -> None:
    request = BacktestRequest(market_kind=MarketKind.SPOT)
    request.market.exchange = ExchangeName.SYNTHETIC
    request.market.limit = 400
    request.strategy.name = StrategyName.MEAN_REVERSION
    candles = asyncio.run(SyntheticAdapter().fetch_candles(request.market))
    response = asyncio.run(run_backtest(request, candles, "synthetic", []))

    assert request.execution.leverage == 1.0
    assert all(trade.side == "long" for trade in response.trades)


def test_flash_crash_scenario_runs() -> None:
    request = BacktestRequest()
    request.market.exchange = ExchangeName.SYNTHETIC
    request.market.limit = 300
    request.scenario.name = ScenarioName.FLASH_CRASH
    candles = asyncio.run(SyntheticAdapter().fetch_candles(request.market))
    response = asyncio.run(run_backtest(request, candles, "synthetic", []))

    assert response.scenario.name == ScenarioName.FLASH_CRASH
    assert response.metrics.max_drawdown_pct >= 0
