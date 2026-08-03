from __future__ import annotations

import hashlib
import json
import math
import time
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
        if not isinstance(payload, dict):
            raise ValueError("Order-book snapshot must be an object")
        try:
            exchange = str(payload["exchange"]).strip()
            symbol = str(payload["symbol"]).strip()
            timestamp_ms = int(payload["timestamp_ms"])
            sequence = int(payload.get("sequence", 0))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Order-book snapshot has invalid metadata") from exc
        if not exchange or not symbol or timestamp_ms < 0 or sequence < 0:
            raise ValueError("Order-book snapshot has invalid metadata")

        levels = payload.get("levels")
        if levels is not None:
            if not isinstance(levels, (list, tuple)) or len(levels) < 2:
                raise ValueError("Order-book levels must contain bids and asks")
            bids_payload = payload.get("bids", levels[0])
            asks_payload = payload.get("asks", levels[1])
        else:
            bids_payload = payload.get("bids", [])
            asks_payload = payload.get("asks", [])

        return cls(
            exchange=exchange,
            symbol=symbol,
            timestamp_ms=timestamp_ms,
            sequence=sequence,
            bids=_normalize_levels(bids_payload, reverse=True),
            asks=_normalize_levels(asks_payload, reverse=False),
            environment=str(payload.get("environment", "simulation")),
        )

    @property
    def crossed(self) -> bool:
        return bool(self.bids and self.asks and self.bids[0].price >= self.asks[0].price)

    @property
    def checksum(self) -> str:
        canonical = json.dumps(
            {
                "exchange": self.exchange,
                "symbol": self.symbol,
                "timestamp_ms": self.timestamp_ms,
                "sequence": self.sequence,
                "environment": self.environment,
                "bids": [(level.price, level.quantity) for level in self.bids],
                "asks": [(level.price, level.quantity) for level in self.asks],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    def is_stale(self, *, now_ms: int | None = None, max_age_ms: int | None = None) -> bool:
        if max_age_ms is None:
            return False
        if max_age_ms < 0:
            raise ValueError("max_age_ms must not be negative")
        observed_at = int(time.time() * 1000) if now_ms is None else now_ms
        return observed_at - self.timestamp_ms > max_age_ms

@dataclass(frozen=True)
class Fill:
    price: float
    quantity: float
    notional: float
    fee: float = 0.0


@dataclass
class ExecutionResult:
    requested_quantity: float
    filled_quantity: float
    remaining_quantity: float
    average_price: float | None
    status: OrderStatus
    fills: list[Fill] = field(default_factory=list)

    @property
    def notional(self) -> float:
        return sum(fill.notional for fill in self.fills)

    @property
    def fees(self) -> float:
        return sum(fill.fee for fill in self.fills)


def simulate_order(
    snapshot: OrderBookSnapshot,
    side: Side,
    quantity: float,
    limit_price: float | None = None,
    fee_bps: float = 0.0,
    *,
    now_ms: int | None = None,
    max_age_ms: int | None = None,
) -> ExecutionResult:
    if (
        not math.isfinite(quantity)
        or quantity <= 0
        or (side != Side.BUY and side != Side.SELL)
        or not math.isfinite(fee_bps)
        or fee_bps < 0
        or (limit_price is not None and (not math.isfinite(limit_price) or limit_price <= 0))
        or snapshot.crossed
        or snapshot.is_stale(now_ms=now_ms, max_age_ms=max_age_ms)
    ):
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
        notional = level.price * filled
        fills.append(Fill(level.price, filled, notional, notional * fee_bps / 10_000))
        remaining = max(0.0, remaining - filled)

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
    snapshots = [
        payload if isinstance(payload, OrderBookSnapshot) else OrderBookSnapshot.from_payload(payload)
        for payload in payloads
    ]
    unique = {snapshot.checksum: snapshot for snapshot in snapshots}
    return sorted(
        unique.values(),
        key=lambda item: (item.timestamp_ms, item.sequence, item.exchange, item.symbol, item.checksum),
    )


def _normalize_levels(raw_levels: object, *, reverse: bool) -> tuple[BookLevel, ...]:
    if raw_levels is None:
        return ()
    if not isinstance(raw_levels, (list, tuple)):
        raise ValueError("Order-book levels must be an array")

    quantities: dict[float, float] = {}
    for raw_level in raw_levels:
        if isinstance(raw_level, dict):
            raw_price, raw_quantity = raw_level.get("px"), raw_level.get("sz")
        elif isinstance(raw_level, (list, tuple)) and len(raw_level) == 2:
            raw_price, raw_quantity = raw_level
        else:
            raise ValueError("Each order-book level must contain price and quantity")
        try:
            price = float(raw_price)
            quantity = float(raw_quantity)
        except (TypeError, ValueError) as exc:
            raise ValueError("Order-book levels must be numeric") from exc
        if not math.isfinite(price) or not math.isfinite(quantity) or price <= 0 or quantity <= 0:
            raise ValueError("Order-book levels must be finite and positive")
        quantities[price] = quantities.get(price, 0.0) + quantity

    return tuple(
        BookLevel(price, quantity)
        for price, quantity in sorted(quantities.items(), reverse=reverse)
    )
