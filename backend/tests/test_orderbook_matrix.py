import math

import pytest

from app.research.orderbook import BookLevel, OrderBookSnapshot, OrderStatus, Side, replay_snapshots, simulate_order


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


def test_snapshot_levels_are_sorted_deduplicated_and_checksum_stable():
    first = book(asks=[[101, 0.25], [100, 0.5], [100, 0.25]], bids=[[99, 1], [100, 1]])
    second = book(asks=[[100, 0.75], [101, 0.25]], bids=[[100, 1], [99, 1]])

    assert [(level.price, level.quantity) for level in first.asks] == [(100, 0.75), (101, 0.25)]
    assert [(level.price, level.quantity) for level in first.bids] == [(100, 1), (99, 1)]
    assert first.checksum == second.checksum
    assert len(replay_snapshots([first, second])) == 1


def test_direct_snapshot_construction_uses_same_canonical_levels():
    snapshot = OrderBookSnapshot(
        exchange="test",
        symbol="BTC",
        timestamp_ms=1000,
        sequence=1,
        bids=(BookLevel(99, 1), BookLevel(100, 0.5)),
        asks=(BookLevel(102, 1), BookLevel(101, 1)),
    )

    assert [level.price for level in snapshot.bids] == [100, 99]
    assert [level.price for level in snapshot.asks] == [101, 102]


def test_crossed_and_stale_books_are_rejected_without_fills():
    crossed = book(asks=[[100, 1]], bids=[[100, 1]])
    stale = book(asks=[[100, 1]], timestamp_ms=1)

    assert simulate_order(crossed, Side.BUY, 1).status == OrderStatus.REJECTED
    assert simulate_order(stale, Side.BUY, 1, now_ms=1001, max_age_ms=100).status == OrderStatus.REJECTED


def test_malformed_levels_fail_closed():
    with pytest.raises(ValueError):
        book(asks=[["not-a-price", 1]])
    with pytest.raises(ValueError):
        book(asks=[[100, -1]])


def test_fees_and_notional_are_symmetric_for_buy_and_sell():
    buy = simulate_order(book(asks=[[100, 0.5], [101, 0.5]]), Side.BUY, 1, fee_bps=10)
    sell = simulate_order(book(bids=[[101, 0.5], [100, 0.5]]), Side.SELL, 1, fee_bps=10)

    assert buy.notional == pytest.approx(100.5)
    assert sell.notional == pytest.approx(100.5)
    assert buy.fees == pytest.approx(0.1005)
    assert sell.fees == pytest.approx(0.1005)
