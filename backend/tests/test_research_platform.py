from __future__ import annotations

from app.research.engine import (
    BookQuote,
    CrossExchangeArbitrageEngine,
    InventoryMarketMaker,
    monte_carlo_resample,
    pair_arbitrage_intents,
    parameter_combinations,
    walk_forward_windows,
)
from app.research.events import EventKind, EventSequencer, MarketEvent, normalize_hyperliquid_message
from app.research.execution import TestnetOrderRequest as OrderRequest, TestnetSafetyGate as SafetyGate


def test_hyperliquid_trade_normalization_is_deterministic() -> None:
    sequencer = EventSequencer()
    events = normalize_hyperliquid_message(
        {"channel": "trades", "data": [{"coin": "BTC", "px": "100", "sz": "1", "time": 1000}]},
        sequencer,
        receive_time_ns=2_000_000_000,
    )
    assert len(events) == 1
    assert events[0].kind == EventKind.TRADE
    rebuilt = MarketEvent.build(
        sequence=1,
        exchange="hyperliquid",
        symbol="BTC",
        kind=EventKind.TRADE,
        event_time_ns=1_000_000_000_000,
        receive_time_ns=2_000_000_000,
        payload={"coin": "BTC", "px": "100", "sz": "1", "time": 1000},
    )
    assert events[0].checksum == rebuilt.checksum


def test_cross_exchange_arbitrage_detects_net_edge() -> None:
    engine = CrossExchangeArbitrageEngine(min_edge_bps=5, fee_bps=1, max_quantity=2)
    engine.update(BookQuote("a", "BTC", 99, 100, 3, 3, 1))
    opportunities = engine.update(BookQuote("b", "BTC", 101, 102, 4, 4, 1))
    assert opportunities
    assert opportunities[0].buy_exchange == "a"
    assert opportunities[0].sell_exchange == "b"
    assert opportunities[0].quantity == 2


def test_arbitrage_intents_pair_deterministically_and_present_expected_profit() -> None:
    intents = [
        {"exchange": "sell-venue", "symbol": "BTC", "side": "sell", "quantity": 2, "limit_price": 101, "filled": True, "timestamp_ns": 10, "metadata": {"arb_leg": "sell", "edge_bps": 80}},
        {"exchange": "buy-venue", "symbol": "BTC", "side": "buy", "quantity": 1.5, "limit_price": 100, "filled": True, "timestamp_ns": 10, "metadata": {"arb_leg": "buy", "edge_bps": 80}},
    ]

    rows = pair_arbitrage_intents(intents, fee_bps=2)

    assert rows == [
        {
            "timestamp_ns": 10,
            "symbol": "BTC",
            "buy_venue": "buy-venue",
            "sell_venue": "sell-venue",
            "buy_price": 100.0,
            "sell_price": 101.0,
            "quantity": 1.5,
            "gross_edge_bps": 100.0,
            "expected_edge_bps": 80.0,
            "estimated_profit": 1.2,
            "buy_filled": True,
            "sell_filled": True,
        }
    ]


def test_inventory_quotes_skew_away_from_long_inventory() -> None:
    model = InventoryMarketMaker(spread_bps=10, inventory_skew_bps=5, max_inventory=10)
    neutral = model.quotes(100, 0)
    long = model.quotes(100, 10)
    assert long[0] < neutral[0]
    assert long[1] < neutral[1]


def test_research_utilities_are_seeded_and_complete() -> None:
    assert len(parameter_combinations({"a": 1}, {"b": [2, 3], "c": [4, 5]})) == 4
    assert walk_forward_windows(100, 4)
    first = monte_carlo_resample([0.01, -0.02, 0.03], runs=100, seed=11)
    second = monte_carlo_resample([0.01, -0.02, 0.03], runs=100, seed=11)
    assert first == second


def test_execution_gate_defaults_to_denied(monkeypatch) -> None:
    monkeypatch.delenv("QUANTFORGE_TESTNET_EXECUTION_ENABLED", raising=False)
    monkeypatch.delenv("QUANTFORGE_EXECUTION_NETWORK", raising=False)
    request = OrderRequest(
        symbol="BTC", side="buy", size=0.001, limit_price=100, submit=True, acknowledgement="I_UNDERSTAND_THIS_IS_TESTNET"
    )
    try:
        SafetyGate().validate(request, "bad")
    except PermissionError:
        pass
    else:
        raise AssertionError("Execution gate must deny by default")
