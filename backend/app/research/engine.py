from __future__ import annotations

import itertools
import math
import random
import statistics
from dataclasses import dataclass, field
from typing import Any, Iterable

from pydantic import BaseModel, Field

from .events import EventKind, MarketEvent, event_sort_key


@dataclass(frozen=True)
class PositionKey:
    exchange: str
    symbol: str


@dataclass
class Position:
    quantity: float = 0.0
    average_price: float = 0.0
    realized_pnl: float = 0.0


@dataclass
class Fill:
    exchange: str
    symbol: str
    side: str
    quantity: float
    price: float
    fee: float = 0.0
    timestamp_ns: int = 0


class Portfolio:
    def __init__(self, starting_cash: float = 100_000.0) -> None:
        self.cash: dict[str, float] = {"USD": starting_cash}
        self.positions: dict[PositionKey, Position] = {}
        self.marks: dict[PositionKey, float] = {}
        self.funding_paid = 0.0
        self.fees_paid = 0.0

    def mark(self, exchange: str, symbol: str, price: float) -> None:
        if price > 0:
            self.marks[PositionKey(exchange, symbol)] = price

    def apply_fill(self, fill: Fill) -> None:
        key = PositionKey(fill.exchange, fill.symbol)
        position = self.positions.setdefault(key, Position())
        signed = fill.quantity if fill.side == "buy" else -fill.quantity
        old_quantity = position.quantity
        new_quantity = old_quantity + signed
        if old_quantity == 0 or old_quantity * signed > 0:
            total_cost = position.average_price * abs(old_quantity) + fill.price * abs(signed)
            position.average_price = total_cost / max(abs(new_quantity), 1e-12)
        else:
            closing = min(abs(old_quantity), abs(signed))
            direction = 1 if old_quantity > 0 else -1
            position.realized_pnl += closing * (fill.price - position.average_price) * direction
            if new_quantity == 0:
                position.average_price = 0.0
            elif old_quantity * new_quantity < 0:
                position.average_price = fill.price
        position.quantity = new_quantity
        self.cash["USD"] -= signed * fill.price + fill.fee
        self.fees_paid += fill.fee
        self.mark(fill.exchange, fill.symbol, fill.price)

    def apply_funding(self, exchange: str, symbol: str, rate: float) -> float:
        key = PositionKey(exchange, symbol)
        position = self.positions.get(key)
        mark = self.marks.get(key)
        if not position or not mark:
            return 0.0
        payment = position.quantity * mark * rate
        self.cash["USD"] -= payment
        self.funding_paid += payment
        return payment

    def equity(self) -> float:
        value = self.cash.get("USD", 0.0)
        for key, position in self.positions.items():
            value += position.quantity * self.marks.get(key, position.average_price)
        return value

    def snapshot(self) -> dict[str, Any]:
        return {
            "cash": self.cash.copy(),
            "equity": self.equity(),
            "fees_paid": self.fees_paid,
            "funding_paid": self.funding_paid,
            "positions": [
                {
                    "exchange": key.exchange,
                    "symbol": key.symbol,
                    "quantity": value.quantity,
                    "average_price": value.average_price,
                    "realized_pnl": value.realized_pnl,
                    "mark": self.marks.get(key),
                }
                for key, value in sorted(self.positions.items(), key=lambda item: (item[0].exchange, item[0].symbol))
            ],
        }


@dataclass
class BookQuote:
    exchange: str
    symbol: str
    bid: float
    ask: float
    bid_size: float
    ask_size: float
    timestamp_ns: int


@dataclass
class ArbitrageOpportunity:
    symbol: str
    buy_exchange: str
    sell_exchange: str
    buy_price: float
    sell_price: float
    quantity: float
    gross_edge_bps: float
    expected_edge_bps: float


class CrossExchangeArbitrageEngine:
    def __init__(self, min_edge_bps: float = 5.0, fee_bps: float = 2.0, max_quantity: float = 1.0) -> None:
        self.min_edge_bps = min_edge_bps
        self.fee_bps = fee_bps
        self.max_quantity = max_quantity
        self.books: dict[tuple[str, str], BookQuote] = {}

    def update(self, quote: BookQuote) -> list[ArbitrageOpportunity]:
        self.books[(quote.exchange, quote.symbol)] = quote
        return self.scan(quote.symbol)

    def scan(self, symbol: str) -> list[ArbitrageOpportunity]:
        books = [book for (_, candidate), book in self.books.items() if candidate == symbol]
        opportunities: list[ArbitrageOpportunity] = []
        for buy, sell in itertools.permutations(books, 2):
            if buy.exchange == sell.exchange or buy.ask <= 0:
                continue
            gross = (sell.bid - buy.ask) / buy.ask * 10_000
            expected = gross - 2 * self.fee_bps
            if expected >= self.min_edge_bps:
                opportunities.append(
                    ArbitrageOpportunity(
                        symbol=symbol,
                        buy_exchange=buy.exchange,
                        sell_exchange=sell.exchange,
                        buy_price=buy.ask,
                        sell_price=sell.bid,
                        quantity=min(buy.ask_size, sell.bid_size, self.max_quantity),
                        gross_edge_bps=gross,
                        expected_edge_bps=expected,
                    )
                )
        return sorted(opportunities, key=lambda item: item.expected_edge_bps, reverse=True)


@dataclass
class QueueOrder:
    order_id: str
    side: str
    price: float
    remaining: float
    queue_ahead: float
    filled: float = 0.0


class QueuePositionSimulator:
    def __init__(self, join_fraction: float = 1.0, cancel_ahead_probability: float = 0.15, seed: int = 7) -> None:
        self.join_fraction = max(join_fraction, 0.0)
        self.cancel_ahead_probability = min(max(cancel_ahead_probability, 0.0), 1.0)
        self.random = random.Random(seed)
        self.orders: dict[str, QueueOrder] = {}

    def place(self, order_id: str, side: str, price: float, quantity: float, level_size: float) -> QueueOrder:
        order = QueueOrder(order_id, side, price, quantity, level_size * self.join_fraction)
        self.orders[order_id] = order
        return order

    def on_trade(self, trade_side: str, price: float, quantity: float) -> list[tuple[str, float]]:
        fills: list[tuple[str, float]] = []
        for order in self.orders.values():
            crosses = (order.side == "buy" and trade_side == "sell" and price <= order.price) or (
                order.side == "sell" and trade_side == "buy" and price >= order.price
            )
            if not crosses or order.remaining <= 0:
                continue
            cancelled_ahead = order.queue_ahead * self.cancel_ahead_probability * self.random.random()
            order.queue_ahead = max(order.queue_ahead - cancelled_ahead, 0.0)
            consumed = max(quantity - order.queue_ahead, 0.0)
            order.queue_ahead = max(order.queue_ahead - quantity, 0.0)
            fill_quantity = min(consumed, order.remaining)
            if fill_quantity > 0:
                order.remaining -= fill_quantity
                order.filled += fill_quantity
                fills.append((order.order_id, fill_quantity))
        return fills


class InventoryMarketMaker:
    def __init__(self, spread_bps: float = 8.0, inventory_skew_bps: float = 3.0, max_inventory: float = 5.0) -> None:
        self.spread_bps = spread_bps
        self.inventory_skew_bps = inventory_skew_bps
        self.max_inventory = max_inventory

    def quotes(self, mid: float, inventory: float, volatility: float = 0.0) -> tuple[float, float]:
        normalized_inventory = max(min(inventory / max(self.max_inventory, 1e-12), 1.0), -1.0)
        skew = normalized_inventory * self.inventory_skew_bps / 10_000
        half_spread = (self.spread_bps + volatility * 10_000) / 20_000
        reservation = mid * (1 - skew)
        return reservation * (1 - half_spread), reservation * (1 + half_spread)


class OrderIntent(BaseModel):
    exchange: str
    symbol: str
    side: str
    quantity: float = Field(gt=0)
    limit_price: float | None = None
    maker_only: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


def pair_arbitrage_intents(intents: list[dict[str, Any]], fee_bps: float = 2.0) -> list[dict[str, Any]]:
    groups: dict[tuple[int, str, str], dict[str, list[dict[str, Any]]]] = {}
    for intent in intents:
        if intent.get("side") not in {"buy", "sell"}:
            continue
        metadata = intent.get("metadata") if isinstance(intent.get("metadata"), dict) else {}
        key = (
            int(intent.get("timestamp_ns", 0)),
            str(intent.get("symbol", "")),
            str(metadata.get("edge_bps", "")),
        )
        groups.setdefault(key, {"buy": [], "sell": []})[intent["side"]].append(intent)

    opportunities: list[dict[str, Any]] = []
    for (timestamp_ns, symbol, _), group in groups.items():
        buys = sorted(group["buy"], key=lambda item: str(item.get("exchange", "")))
        sells = sorted(group["sell"], key=lambda item: str(item.get("exchange", "")))
        for buy, sell in zip(buys, sells):
            buy_price = float(buy.get("limit_price") or 0)
            sell_price = float(sell.get("limit_price") or 0)
            quantity = min(float(buy.get("quantity") or 0), float(sell.get("quantity") or 0))
            if buy_price <= 0 or sell_price <= 0 or quantity <= 0:
                continue
            gross_edge_bps = (sell_price - buy_price) / buy_price * 10_000
            metadata = buy.get("metadata") if isinstance(buy.get("metadata"), dict) else {}
            expected_edge_bps = float(metadata.get("edge_bps", gross_edge_bps - 2 * fee_bps))
            opportunities.append(
                {
                    "timestamp_ns": timestamp_ns,
                    "symbol": symbol,
                    "buy_venue": str(buy.get("exchange", "")),
                    "sell_venue": str(sell.get("exchange", "")),
                    "buy_price": buy_price,
                    "sell_price": sell_price,
                    "quantity": quantity,
                    "gross_edge_bps": gross_edge_bps,
                    "expected_edge_bps": expected_edge_bps,
                    "estimated_profit": buy_price * quantity * expected_edge_bps / 10_000,
                    "buy_filled": bool(buy.get("filled")),
                    "sell_filled": bool(sell.get("filled")),
                }
            )
    return sorted(opportunities, key=lambda item: (item["timestamp_ns"], item["buy_venue"], item["sell_venue"]))


@dataclass
class StrategyContext:
    portfolio: Portfolio
    event: MarketEvent
    books: dict[tuple[str, str], BookQuote]
    intents: list[OrderIntent] = field(default_factory=list)

    def order(self, intent: OrderIntent) -> None:
        self.intents.append(intent)


class Strategy:
    name = "base"

    def __init__(self, **parameters: Any) -> None:
        self.parameters = parameters

    def on_book(self, context: StrategyContext) -> None:
        pass

    def on_trade(self, context: StrategyContext) -> None:
        pass

    def on_funding(self, context: StrategyContext) -> None:
        pass

    def on_timer(self, context: StrategyContext) -> None:
        pass


class CrossVenueArbitrageStrategy(Strategy):
    name = "cross_exchange_arbitrage"

    def __init__(self, **parameters: Any) -> None:
        super().__init__(**parameters)
        self.engine = CrossExchangeArbitrageEngine(
            min_edge_bps=float(parameters.get("min_edge_bps", 5.0)),
            fee_bps=float(parameters.get("fee_bps", 2.0)),
            max_quantity=float(parameters.get("max_quantity", 1.0)),
        )

    def on_book(self, context: StrategyContext) -> None:
        quote = context.books.get((context.event.exchange, context.event.symbol))
        if not quote:
            return
        opportunities = self.engine.update(quote)
        if not opportunities:
            return
        best = opportunities[0]
        context.order(
            OrderIntent(
                exchange=best.buy_exchange,
                symbol=best.symbol,
                side="buy",
                quantity=best.quantity,
                limit_price=best.buy_price,
                maker_only=False,
                metadata={"arb_leg": "buy", "edge_bps": best.expected_edge_bps},
            )
        )
        context.order(
            OrderIntent(
                exchange=best.sell_exchange,
                symbol=best.symbol,
                side="sell",
                quantity=best.quantity,
                limit_price=best.sell_price,
                maker_only=False,
                metadata={"arb_leg": "sell", "edge_bps": best.expected_edge_bps},
            )
        )


class InventoryMarketMakingStrategy(Strategy):
    name = "inventory_market_making"

    def __init__(self, **parameters: Any) -> None:
        super().__init__(**parameters)
        self.model = InventoryMarketMaker(
            spread_bps=float(parameters.get("spread_bps", 8.0)),
            inventory_skew_bps=float(parameters.get("inventory_skew_bps", 3.0)),
            max_inventory=float(parameters.get("max_inventory", 5.0)),
        )
        self.quantity = float(parameters.get("quantity", 0.01))

    def on_timer(self, context: StrategyContext) -> None:
        for (exchange, symbol), quote in context.books.items():
            position = context.portfolio.positions.get(PositionKey(exchange, symbol), Position())
            mid = (quote.bid + quote.ask) / 2
            bid, ask = self.model.quotes(mid, position.quantity)
            context.order(OrderIntent(exchange=exchange, symbol=symbol, side="buy", quantity=self.quantity, limit_price=bid, maker_only=True))
            context.order(OrderIntent(exchange=exchange, symbol=symbol, side="sell", quantity=self.quantity, limit_price=ask, maker_only=True))


STRATEGIES: dict[str, type[Strategy]] = {
    CrossVenueArbitrageStrategy.name: CrossVenueArbitrageStrategy,
    InventoryMarketMakingStrategy.name: InventoryMarketMakingStrategy,
}


def make_strategy(name: str, parameters: dict[str, Any] | None = None) -> Strategy:
    try:
        strategy_type = STRATEGIES[name]
    except KeyError as exc:
        raise ValueError(f"Unknown event strategy: {name}") from exc
    return strategy_type(**(parameters or {}))


class ReplayResult(BaseModel):
    strategy: str
    event_count: int
    timer_count: int
    order_intent_count: int
    fill_count: int
    starting_equity: float
    final_equity: float
    return_pct: float
    max_drawdown_pct: float
    portfolio: dict[str, Any]
    intents: list[dict[str, Any]]
    opportunities: list[dict[str, Any]]
    equity_curve: list[dict[str, Any]]


class DeterministicReplayEngine:
    def __init__(self, timer_interval_ms: int = 1_000, fee_bps: float = 2.0) -> None:
        self.timer_interval_ns = max(timer_interval_ms, 1) * 1_000_000
        self.fee_bps = fee_bps

    def run(self, events: Iterable[MarketEvent], strategy: Strategy, starting_cash: float = 100_000.0) -> ReplayResult:
        ordered = sorted(list(events), key=event_sort_key)
        portfolio = Portfolio(starting_cash)
        books: dict[tuple[str, str], BookQuote] = {}
        all_intents: list[dict[str, Any]] = []
        curve: list[dict[str, Any]] = []
        fill_count = 0
        timer_count = 0
        next_timer = ordered[0].event_time_ns if ordered else 0
        peak = starting_cash
        max_drawdown = 0.0

        def dispatch(event: MarketEvent) -> None:
            nonlocal fill_count, peak, max_drawdown
            self._apply_market_state(event, portfolio, books)
            context = StrategyContext(portfolio=portfolio, event=event, books=books)
            callback = {
                EventKind.BOOK: strategy.on_book,
                EventKind.TRADE: strategy.on_trade,
                EventKind.FUNDING: strategy.on_funding,
                EventKind.TIMER: strategy.on_timer,
            }.get(event.kind)
            if callback:
                callback(context)
            for intent in context.intents:
                fill = self._simulate_fill(intent, books, event.event_time_ns)
                record = intent.model_dump()
                record["timestamp_ns"] = event.event_time_ns
                record["filled"] = fill is not None
                all_intents.append(record)
                if fill:
                    portfolio.apply_fill(fill)
                    fill_count += 1
            equity = portfolio.equity()
            peak = max(peak, equity)
            if peak > 0:
                max_drawdown = max(max_drawdown, (peak - equity) / peak * 100)
            curve.append({"timestamp_ns": event.event_time_ns, "equity": equity})

        for event in ordered:
            while next_timer and next_timer <= event.event_time_ns:
                timer_count += 1
                dispatch(
                    MarketEvent.build(
                        sequence=10**12 + timer_count,
                        exchange="scheduler",
                        symbol="*",
                        kind=EventKind.TIMER,
                        event_time_ns=next_timer,
                        receive_time_ns=next_timer,
                        payload={"timer_index": timer_count},
                    )
                )
                next_timer += self.timer_interval_ns
            dispatch(event)

        final = portfolio.equity()
        return ReplayResult(
            strategy=strategy.name,
            event_count=len(ordered),
            timer_count=timer_count,
            order_intent_count=len(all_intents),
            fill_count=fill_count,
            starting_equity=starting_cash,
            final_equity=final,
            return_pct=(final / starting_cash - 1) * 100 if starting_cash else 0.0,
            max_drawdown_pct=max_drawdown,
            portfolio=portfolio.snapshot(),
            intents=all_intents[-500:],
            opportunities=pair_arbitrage_intents(all_intents[-500:], self.fee_bps),
            equity_curve=curve,
        )

    def _apply_market_state(
        self, event: MarketEvent, portfolio: Portfolio, books: dict[tuple[str, str], BookQuote]
    ) -> None:
        if event.kind == EventKind.MID:
            try:
                portfolio.mark(event.exchange, event.symbol, float(event.payload["mid"]))
            except (KeyError, TypeError, ValueError):
                pass
        elif event.kind == EventKind.TRADE:
            try:
                portfolio.mark(event.exchange, event.symbol, float(event.payload["px"]))
            except (KeyError, TypeError, ValueError):
                pass
        elif event.kind == EventKind.FUNDING:
            try:
                portfolio.apply_funding(event.exchange, event.symbol, float(event.payload["funding"]))
            except (KeyError, TypeError, ValueError):
                pass
        elif event.kind == EventKind.BOOK:
            levels = event.payload.get("levels")
            if not isinstance(levels, list) or len(levels) < 2 or not levels[0] or not levels[1]:
                return
            try:
                bid, ask = levels[0][0], levels[1][0]
                quote = BookQuote(
                    exchange=event.exchange,
                    symbol=event.symbol,
                    bid=float(bid["px"]),
                    ask=float(ask["px"]),
                    bid_size=float(bid["sz"]),
                    ask_size=float(ask["sz"]),
                    timestamp_ns=event.event_time_ns,
                )
                books[(event.exchange, event.symbol)] = quote
                portfolio.mark(event.exchange, event.symbol, (quote.bid + quote.ask) / 2)
            except (KeyError, TypeError, ValueError):
                return

    def _simulate_fill(
        self, intent: OrderIntent, books: dict[tuple[str, str], BookQuote], timestamp_ns: int
    ) -> Fill | None:
        quote = books.get((intent.exchange, intent.symbol))
        if not quote:
            return None
        executable = quote.ask if intent.side == "buy" else quote.bid
        if intent.limit_price is not None:
            if intent.side == "buy" and intent.limit_price < executable:
                return None
            if intent.side == "sell" and intent.limit_price > executable:
                return None
        price = executable
        fee = price * intent.quantity * self.fee_bps / 10_000
        return Fill(intent.exchange, intent.symbol, intent.side, intent.quantity, price, fee, timestamp_ns)


def parameter_combinations(base: dict[str, Any], grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    if not grid:
        return [base.copy()]
    keys = sorted(grid)
    combinations: list[dict[str, Any]] = []
    for values in itertools.product(*(grid[key] for key in keys)):
        item = base.copy()
        item.update(dict(zip(keys, values, strict=True)))
        combinations.append(item)
    return combinations


def walk_forward_windows(length: int, folds: int = 4, train_ratio: float = 0.7) -> list[tuple[slice, slice]]:
    if length < 4:
        return [(slice(0, max(length - 1, 0)), slice(max(length - 1, 0), length))]
    folds = max(1, min(folds, length // 2))
    test_size = max(1, length // (folds + 1))
    windows: list[tuple[slice, slice]] = []
    for fold in range(folds):
        test_end = length - (folds - fold - 1) * test_size
        test_start = max(test_end - test_size, 1)
        train_end = test_start
        train_start = max(0, train_end - max(int(train_end * train_ratio), test_size))
        windows.append((slice(train_start, train_end), slice(test_start, test_end)))
    return windows


def monte_carlo_resample(
    returns: list[float], runs: int = 500, block_size: int = 5, seed: int = 7
) -> dict[str, float]:
    if not returns or runs <= 0:
        return {"p05": 0.0, "median": 0.0, "p95": 0.0, "loss_probability": 0.0}
    rng = random.Random(seed)
    block_size = max(1, min(block_size, len(returns)))
    totals: list[float] = []
    for _ in range(runs):
        sampled: list[float] = []
        while len(sampled) < len(returns):
            start = rng.randrange(0, max(len(returns) - block_size + 1, 1))
            sampled.extend(returns[start : start + block_size])
        compounded = math.prod(1 + value for value in sampled[: len(returns)]) - 1
        totals.append(compounded)
    totals.sort()

    def percentile(fraction: float) -> float:
        index = min(max(round((len(totals) - 1) * fraction), 0), len(totals) - 1)
        return totals[index]

    return {
        "p05": percentile(0.05),
        "median": statistics.median(totals),
        "p95": percentile(0.95),
        "loss_probability": sum(value < 0 for value in totals) / len(totals),
    }
