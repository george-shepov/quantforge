from __future__ import annotations

import pytest

from app.research.engine import (
    BookQuote,
    CrossExchangeArbitrageEngine,
    InventoryMarketMaker,
    monte_carlo_resample,
    parameter_combinations,
    scan_arbitrage_events,
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


def test_arbitrage_candidates_preserve_calculation_and_explain_rejection() -> None:
    engine = CrossExchangeArbitrageEngine(min_edge_bps=5, fee_bps=2, max_quantity=1)
    engine.update(BookQuote("buy", "BTC", 99, 100, 3, 0.8, 1))

    candidates = engine.update_candidates(BookQuote("sell", "BTC", 100.05, 101, 0.4, 2, 2))

    accepted = engine.scan("BTC")
    assert not accepted
    rejected = next(item for item in candidates if item.buy_exchange == "buy" and item.sell_exchange == "sell")
    assert rejected.gross_edge_bps == pytest.approx(5)
    assert rejected.fee_cost_bps == 4
    assert rejected.expected_edge_bps == pytest.approx(1)
    assert rejected.quantity == 0.4
    assert rejected.decision == "rejected"
    assert "below" in rejected.explanation


def test_arbitrage_scan_anchors_both_quotes_and_only_rechecks_updated_pairs() -> None:
    def book(sequence: int, exchange: str, bid: float, ask: float) -> MarketEvent:
        return MarketEvent.build(
            sequence=sequence,
            exchange=exchange,
            symbol="BTC",
            kind=EventKind.BOOK,
            event_time_ns=sequence * 1_000_000,
            receive_time_ns=sequence * 1_000_000,
            payload={
                "levels": [
                    [{"px": str(bid), "sz": "1"}],
                    [{"px": str(ask), "sz": "1"}],
                ]
            },
        )

    events = [
        book(1, "venue-a", 99, 100),
        book(2, "venue-b", 101, 102),
        book(3, "venue-c", 100, 101),
    ]
    output = scan_arbitrage_events(events, dataset_id="three-venues", limit=10)

    assert output["candidate_count"] == 6
    latest = [item for item in output["opportunities"] if item["timestamp_ns"] == 3_000_000]
    assert len(latest) == 4
    assert all("venue-c" in {item["buy_exchange"], item["sell_exchange"]} for item in latest)

    checksums = {event.exchange: event.checksum for event in events}
    for item in output["opportunities"]:
        assert item["buy_source_event_checksum"] == checksums[item["buy_exchange"]]
        assert item["sell_source_event_checksum"] == checksums[item["sell_exchange"]]
    assert len({item["opportunity_id"] for item in output["opportunities"]}) == 6


def test_arbitrage_scan_retains_only_the_bounded_response_window() -> None:
    events = [
        MarketEvent.build(
            sequence=sequence,
            exchange=f"venue-{sequence}",
            symbol="BTC",
            kind=EventKind.BOOK,
            event_time_ns=sequence,
            receive_time_ns=sequence,
            payload={"levels": [[{"px": "99", "sz": "1"}], [{"px": "100", "sz": "1"}]]},
        )
        for sequence in range(1, 8)
    ]

    output = scan_arbitrage_events(events, dataset_id="bounded", limit=3)

    assert output["candidate_count"] == 3
    assert len(output["opportunities"]) == 3
    assert output["accepted_count"] + output["rejected_count"] == 3


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
