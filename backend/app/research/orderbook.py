from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"


@dataclass(frozen=True)
class BookLevel:
    price: float
    quantity: float


@dataclass(frozen=True)
class OrderBookSnapshot:
    exchange: str
    symbol: str
    timestamp_ms: int
    sequence: int
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]
    environment: str = "simulation"

    @classmethod
    def from_payload(cls, payload: dict) -> "OrderBookSnapshot":
        return cls(
            exchange=str(payload["exchange"]),
            symbol=str(payload["symbol"]),
            timestamp_ms=int(payload["timestamp_ms"]),
            sequence=int(payload.get("sequence", 0)),
            bids=tuple(BookLevel(float(p), float(q)) for p, q in payload.get("bids", [])),
            asks=tuple(BookLevel(float(p), float(q)) for p, q in payload.get("asks", [])),
            environment=str(payload.get("environment", "simulation")),
        )


@dataclass(frozen=True)
class Fill:
    price: float
    quantity: float
    notional: float


@dataclass
class ExecutionResult:
    requested_quantity: float
    filled_quantity: float
    remaining_quantity: float
    average_price: float | None
    status: OrderStatus
    fills: list[Fill] = field(default_factory=list)


def simulate_order(
    snapshot: OrderBookSnapshot,
    side: Side,
    quantity: float,
    limit_price: float | None = None,
) -> ExecutionResult:
    if quantity <= 0:
        return ExecutionResult(quantity, 0.0, quantity, None, OrderStatus.REJECTED)

    levels = snapshot.asks if side == Side.BUY else snapshot.bids
    remaining = quantity
    fills: list[Fill] = []
    for level in levels:
        if remaining <= 1e-12:
            break
        if limit_price is not None:
            crosses = level.price <= limit_price if side == Side.BUY else level.price >= limit_price
            if not crosses:
                break
        filled = min(remaining, level.quantity)
        fills.append(Fill(level.price, filled, level.price * filled))
        remaining -= filled

    filled_quantity = quantity - remaining
    average_price = (
        sum(fill.notional for fill in fills) / filled_quantity if filled_quantity > 0 else None
    )
    if filled_quantity <= 0:
        status = OrderStatus.OPEN if limit_price is not None else OrderStatus.REJECTED
    elif remaining > 1e-12:
        status = OrderStatus.PARTIALLY_FILLED
    else:
        status = OrderStatus.FILLED
    return ExecutionResult(quantity, filled_quantity, max(0.0, remaining), average_price, status, fills)


def replay_snapshots(payloads: Iterable[dict]) -> list[OrderBookSnapshot]:
    snapshots = [OrderBookSnapshot.from_payload(payload) for payload in payloads]
    return sorted(snapshots, key=lambda item: (item.timestamp_ms, item.sequence, item.exchange, item.symbol))
