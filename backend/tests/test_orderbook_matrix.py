import math

import pytest

from app.research.orderbook import OrderBookSnapshot, OrderStatus, Side, replay_snapshots, simulate_order


def book(*, asks=(), bids=(), timestamp_ms=1000, sequence=1):
    return OrderBookSnapshot.from_payload(
        {
            "exchange": "test",
            "symbol": "BTC",
            "timestamp_ms": timestamp_ms,
            "sequence": sequence,
            "asks": asks,
            "bids": bids,
        }
    )


@pytest.mark.parametrize("quantity", [0, -1, -0.0001])
def test_non_positive_quantity_is_rejected(quantity):
    result = simulate_order(book(asks=[[100, 1]]), Side.BUY, quantity)
    assert result.status == OrderStatus.REJECTED
    assert result.filled_quantity == 0


def test_empty_market_book_is_rejected():
    result = simulate_order(book(), Side.BUY, 1)
    assert result.status == OrderStatus.REJECTED
    assert result.remaining_quantity == 1


def test_empty_limit_book_remains_open():
    result = simulate_order(book(), Side.BUY, 1, limit_price=100)
    assert result.status == OrderStatus.OPEN


def test_buy_limit_never_crosses_more_expensive_level():
    result = simulate_order(book(asks=[[99, 0.25], [100, 0.25], [101, 10]]), Side.BUY, 1, limit_price=100)
    assert result.status == OrderStatus.PARTIALLY_FILLED
    assert result.filled_quantity == 0.5
    assert all(fill.price <= 100 for fill in result.fills)


def test_sell_limit_never_crosses_cheaper_level():
    result = simulate_order(book(bids=[[101, 0.25], [100, 0.25], [99, 10]]), Side.SELL, 1, limit_price=100)
    assert result.status == OrderStatus.PARTIALLY_FILLED
    assert result.filled_quantity == 0.5
    assert all(fill.price >= 100 for fill in result.fills)


def test_average_price_and_notional_are_consistent():
    result = simulate_order(book(asks=[[100, 1], [110, 2]]), Side.BUY, 3)
    assert result.status == OrderStatus.FILLED
    assert result.average_price == pytest.approx(106.6666666667)
    assert sum(fill.notional for fill in result.fills) == pytest.approx(result.average_price * 3)


def test_requested_equals_filled_plus_remaining():
    result = simulate_order(book(asks=[[100, 0.3]]), Side.BUY, 1)
    assert math.isclose(result.requested_quantity, result.filled_quantity + result.remaining_quantity)


def test_replay_stable_tie_breaker_uses_exchange_and_symbol():
    snapshots = replay_snapshots(
        [
            {"exchange": "z", "symbol": "ETH", "timestamp_ms": 1, "sequence": 1},
            {"exchange": "a", "symbol": "ETH", "timestamp_ms": 1, "sequence": 1},
            {"exchange": "a", "symbol": "BTC", "timestamp_ms": 1, "sequence": 1},
        ]
    )
    assert [(item.exchange, item.symbol) for item in snapshots] == [
        ("a", "BTC"),
        ("a", "ETH"),
        ("z", "ETH"),
    ]
