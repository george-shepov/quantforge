from __future__ import annotations

import math
import uuid
from dataclasses import dataclass

import numpy as np

from app.engine.metrics import calculate_metrics
from app.engine.scenarios import apply_scenario
from app.engine.strategies import build_signals
from app.models import (
    BacktestRequest,
    BacktestResponse,
    Candle,
    EquityPoint,
    MarketKind,
    OrderType,
    TradeRecord,
)


@dataclass
class Position:
    side: int
    quantity: float
    entry_price: float
    entry_time: object
    notional: float
    entry_fee: float
    funding: float = 0.0
    max_favorable: float = 0.0
    max_adverse: float = 0.0


async def run_backtest(request: BacktestRequest, candles: list[Candle], source: str, warnings: list[str]) -> BacktestResponse:
    candles, scenario_slippage, funding_rate = apply_scenario(candles, request.scenario)
    closes = np.array([c.close for c in candles], dtype=float)
    signals = build_signals(closes, request.strategy, request.market_kind)

    cash = request.starting_capital
    position: Position | None = None
    trades: list[TradeRecord] = []
    equity_curve: list[EquityPoint] = []
    peak_equity = request.starting_capital
    bars_in_position = 0
    liquidations = 0
    pending_signal: int | None = None

    for i, candle in enumerate(candles):
        signal = int(signals[i])

        # Funding is applied hourly in the simulation; scale it by candle duration.
        if position and request.market_kind != MarketKind.SPOT and i > 0:
            elapsed_hours = max((candle.timestamp - candles[i - 1].timestamp).total_seconds() / 3600.0, 0.0)
            funding_payment = position.side * abs(position.quantity) * candle.open * funding_rate * elapsed_hours
            cash -= funding_payment
            position.funding += funding_payment

        if position:
            bars_in_position += 1
            pnl_pct = position.side * (candle.close / position.entry_price - 1)
            position.max_favorable = max(position.max_favorable, pnl_pct)
            position.max_adverse = min(position.max_adverse, pnl_pct)

            exit_reason: str | None = None
            if request.execution.stop_loss_pct is not None and pnl_pct <= -request.execution.stop_loss_pct:
                exit_reason = "stop_loss"
            elif request.execution.take_profit_pct is not None and pnl_pct >= request.execution.take_profit_pct:
                exit_reason = "take_profit"
            elif _is_liquidated(position, candle, request):
                exit_reason = "liquidation"
                liquidations += 1
            elif signal != position.side:
                exit_reason = "signal_change"

            if exit_reason:
                fill = _exit_fill_price(position.side, candle, request, scenario_slippage, exit_reason)
                cash, trade = _close_position(cash, position, fill, candle, request, len(trades) + 1, exit_reason)
                trades.append(trade)
                position = None
                if exit_reason == "liquidation":
                    pending_signal = 0
                else:
                    pending_signal = signal

        if position is None:
            desired = pending_signal if pending_signal is not None else signal
            pending_signal = None
            if desired != 0 and not (request.market_kind == MarketKind.SPOT and desired < 0):
                fill = _entry_fill_price(desired, candle, request, scenario_slippage)
                if fill is not None:
                    equity = max(cash, 0.0)
                    leverage = 1.0 if request.market_kind == MarketKind.SPOT else request.execution.leverage
                    notional = equity * request.execution.allocation * leverage
                    quantity = desired * notional / fill
                    fee = _fee(notional, request.execution.order_type, request)
                    if request.market_kind == MarketKind.SPOT:
                        required = notional + fee
                        if required <= cash:
                            cash -= required
                            position = Position(desired, quantity, fill, candle.timestamp, notional, fee)
                    elif fee < cash:
                        cash -= fee
                        position = Position(desired, quantity, fill, candle.timestamp, notional, fee)

        equity = _mark_equity(cash, position, candle.close, request.market_kind)
        peak_equity = max(peak_equity, equity)
        drawdown = (peak_equity - equity) / peak_equity * 100 if peak_equity > 0 else 0.0
        equity_curve.append(
            EquityPoint(
                timestamp=candle.timestamp,
                equity=round(equity, 6),
                drawdown_pct=round(drawdown, 6),
                close=candle.close,
                signal=signal,
            )
        )

    if position:
        final = candles[-1]
        cash, trade = _close_position(cash, position, final.close, final, request, len(trades) + 1, "end_of_test")
        trades.append(trade)
        equity_curve[-1].equity = round(cash, 6)

    metrics = calculate_metrics(request.starting_capital, equity_curve, trades, bars_in_position, liquidations)
    if source == "synthetic-fallback":
        warnings.append("Live exchange data was unavailable; the run used deterministic synthetic candles.")
    warnings.append("Bar-based fills are approximations; full queue-position and tick replay are not yet modeled.")

    return BacktestResponse(
        run_id=str(uuid.uuid4()),
        source=source,
        warnings=warnings,
        market=request.market,
        market_kind=request.market_kind,
        strategy=request.strategy,
        execution=request.execution,
        scenario=request.scenario,
        metrics=metrics,
        equity_curve=equity_curve,
        trades=trades,
    )


def _entry_fill_price(side: int, candle: Candle, request: BacktestRequest, scenario_slippage: float) -> float | None:
    if request.execution.order_type == OrderType.MARKET:
        slip = request.execution.base_slippage_bps * scenario_slippage / 10_000
        return candle.open * (1 + slip * side)
    offset = request.execution.limit_offset_bps / 10_000
    limit = candle.open * (1 - offset * side)
    touched = candle.low <= limit if side > 0 else candle.high >= limit
    return limit if touched else None


def _exit_fill_price(
    side: int,
    candle: Candle,
    request: BacktestRequest,
    scenario_slippage: float,
    reason: str,
) -> float:
    if reason == "liquidation":
        return candle.low if side > 0 else candle.high
    slip = request.execution.base_slippage_bps * scenario_slippage / 10_000
    reference = candle.close
    return reference * (1 - slip * side)


def _is_liquidated(position: Position, candle: Candle, request: BacktestRequest) -> bool:
    if request.market_kind == MarketKind.SPOT:
        return False
    worst = candle.low if position.side > 0 else candle.high
    pnl = position.quantity * (worst - position.entry_price)
    initial_margin = position.notional / request.execution.leverage
    maintenance = position.notional * request.execution.maintenance_margin_rate
    return initial_margin + pnl <= maintenance


def _close_position(
    cash: float,
    position: Position,
    exit_price: float,
    candle: Candle,
    request: BacktestRequest,
    trade_id: int,
    reason: str,
) -> tuple[float, TradeRecord]:
    exit_notional = abs(position.quantity) * exit_price
    exit_fee = _fee(exit_notional, OrderType.MARKET, request)
    gross_pnl = position.quantity * (exit_price - position.entry_price)
    fees = position.entry_fee + exit_fee

    if request.market_kind == MarketKind.SPOT:
        cash += exit_notional - exit_fee
        # For spot, principal was removed at entry. Gross P&L is still price P&L.
    else:
        cash += gross_pnl - exit_fee

    net_pnl = gross_pnl - fees - position.funding
    return_pct = net_pnl / max(position.notional / (1 if request.market_kind == MarketKind.SPOT else request.execution.leverage), 1e-12)

    trade = TradeRecord(
        id=trade_id,
        side="long" if position.side > 0 else "short",
        entry_time=position.entry_time,
        exit_time=candle.timestamp,
        entry_price=round(position.entry_price, 8),
        exit_price=round(exit_price, 8),
        quantity=round(abs(position.quantity), 8),
        notional=round(position.notional, 2),
        gross_pnl=round(gross_pnl, 2),
        fees=round(fees, 2),
        funding=round(position.funding, 2),
        net_pnl=round(net_pnl, 2),
        return_pct=round(return_pct * 100, 4),
        exit_reason=reason,
        mae_pct=round(position.max_adverse * 100, 4),
        mfe_pct=round(position.max_favorable * 100, 4),
    )
    return cash, trade


def _mark_equity(cash: float, position: Position | None, price: float, market_kind: MarketKind) -> float:
    if not position:
        return cash
    if market_kind == MarketKind.SPOT:
        return cash + abs(position.quantity) * price
    return cash + position.quantity * (price - position.entry_price)


def _fee(notional: float, order_type: OrderType, request: BacktestRequest) -> float:
    bps = request.execution.maker_fee_bps if order_type == OrderType.LIMIT else request.execution.taker_fee_bps
    return notional * bps / 10_000
