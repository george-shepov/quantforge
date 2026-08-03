from app.exchanges.environment import ExchangeEnvironment, assert_no_mainnet_execution, endpoints_for
from app.research.orderbook import OrderBookSnapshot, OrderStatus, Side, replay_snapshots, simulate_order


def test_exchange_testnet_endpoints_are_explicit_and_read_only():
    bybit = endpoints_for("bybit", ExchangeEnvironment.TESTNET)
    hyperliquid = endpoints_for("hyperliquid", ExchangeEnvironment.TESTNET)
    bitmex = endpoints_for("bitmex", ExchangeEnvironment.TESTNET)

    assert "testnet" in bybit.rest
    assert "testnet" in hyperliquid.rest
    assert "testnet" in bitmex.rest
    assert bybit.websocket and hyperliquid.websocket and bitmex.websocket
    assert not bybit.execution_allowed
    assert not hyperliquid.execution_allowed
    assert not bitmex.execution_allowed


def test_environment_routes_accept_configured_string_values():
    endpoint = endpoints_for("bybit", "demo")

    assert endpoint.environment == ExchangeEnvironment.DEMO
    assert "demo" in endpoint.rest


def test_mainnet_submission_is_always_blocked():
    try:
        assert_no_mainnet_execution(ExchangeEnvironment.MAINNET_READONLY, submit=True)
    except PermissionError as exc:
        assert "disabled" in str(exc).lower()
    else:
        raise AssertionError("mainnet submission must be blocked")


def test_market_order_walks_book_and_partially_fills():
    snapshot = OrderBookSnapshot.from_payload(
        {
            "exchange": "bybit",
            "symbol": "BTC",
            "timestamp_ms": 1000,
            "sequence": 10,
            "asks": [[100.0, 1.0], [101.0, 0.5]],
            "bids": [[99.0, 2.0]],
            "environment": "testnet",
        }
    )
    result = simulate_order(snapshot, Side.BUY, quantity=2.0)

    assert result.status == OrderStatus.PARTIALLY_FILLED
    assert result.filled_quantity == 1.5
    assert result.remaining_quantity == 0.5
    assert result.average_price == (100.0 + 50.5) / 1.5
    assert len(result.fills) == 2


def test_limit_order_stops_at_limit_price():
    snapshot = OrderBookSnapshot.from_payload(
        {
            "exchange": "whitebit",
            "symbol": "BTC",
            "timestamp_ms": 1000,
            "asks": [[100.0, 0.4], [101.0, 1.0]],
            "bids": [],
        }
    )
    result = simulate_order(snapshot, Side.BUY, quantity=1.0, limit_price=100.0)

    assert result.status == OrderStatus.PARTIALLY_FILLED
    assert result.filled_quantity == 0.4
    assert result.remaining_quantity == 0.6


def test_replay_is_deterministic():
    replay = replay_snapshots(
        [
            {"exchange": "b", "symbol": "BTC", "timestamp_ms": 2, "sequence": 1},
            {"exchange": "a", "symbol": "BTC", "timestamp_ms": 1, "sequence": 2},
            {"exchange": "a", "symbol": "BTC", "timestamp_ms": 1, "sequence": 1},
        ]
    )
    assert [(item.timestamp_ms, item.sequence) for item in replay] == [(1, 1), (1, 2), (2, 1)]
