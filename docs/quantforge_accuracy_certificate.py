#!/usr/bin/env python3
"""Independent known-answer checks for QuantForge calculations.

Run from the QuantForge repository root:

    python tools/quantforge_accuracy_certificate.py

The script compares QuantForge outputs with Decimal-based oracle calculations,
writes quantforge-accuracy-certificate.json, and exits non-zero on failure.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from dataclasses import asdict, dataclass
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any

getcontext().prec = 40
TOLERANCE = 1e-10


def locate_backend() -> Path:
    here = Path(__file__).resolve()
    for candidate in (
        Path.cwd(),
        Path.cwd() / "backend",
        here.parent,
        here.parent / "backend",
        here.parent.parent,
        here.parent.parent / "backend",
    ):
        if (candidate / "app" / "research" / "engine.py").is_file():
            return candidate
    raise SystemExit("QuantForge backend not found. Run this inside the repository.")


BACKEND = locate_backend()
sys.path.insert(0, str(BACKEND))

from app.research.engine import (  # noqa: E402
    BookQuote,
    CrossExchangeArbitrageEngine,
    DeterministicReplayEngine,
    make_strategy,
    monte_carlo_resample,
)
from app.research.events import EventKind, MarketEvent  # noqa: E402
from app.research.orderbook import (  # noqa: E402
    OrderBookSnapshot,
    OrderStatus,
    Side,
    simulate_order,
)


@dataclass
class Check:
    name: str
    expected: Any
    actual: Any
    passed: bool
    note: str = ""


checks: list[Check] = []


def D(value: Any) -> Decimal:
    return Decimal(str(value))


def close(actual: Any, expected: Any) -> bool:
    return math.isclose(float(actual), float(expected), rel_tol=TOLERANCE, abs_tol=TOLERANCE)


def check(name: str, expected: Any, actual: Any, passed: bool | None = None, note: str = "") -> None:
    checks.append(Check(name, expected, actual, close(actual, expected) if passed is None else passed, note))


def oracle(buy: Any, sell: Any, quantity: Any, fee_bps: Any, slippage_bps: Any = 0) -> dict[str, Decimal]:
    buy, sell, quantity = D(buy), D(sell), D(quantity)
    fee_bps, slippage_bps = D(fee_bps), D(slippage_bps)
    gross = (sell - buy) / buy * D(10_000)
    expected = gross - D(2) * fee_bps - D(2) * slippage_bps
    scanner = buy * quantity * expected / D(10_000)
    exact = (
        sell * quantity
        - buy * quantity
        - buy * quantity * fee_bps / D(10_000)
        - sell * quantity * fee_bps / D(10_000)
        - buy * quantity * D(2) * slippage_bps / D(10_000)
    )
    return {"gross_bps": gross, "expected_bps": expected, "scanner_profit": scanner, "exact_cash_pnl": exact}


def book_event(sequence: int, exchange: str, bids: list[tuple[float, float]], asks: list[tuple[float, float]]) -> MarketEvent:
    return MarketEvent.build(
        sequence=sequence,
        exchange=exchange,
        symbol="BTC",
        kind=EventKind.BOOK,
        event_time_ns=sequence * 1_000_000,
        receive_time_ns=sequence * 1_000_000,
        payload={
            "levels": [
                [{"px": str(price), "sz": str(size)} for price, size in bids],
                [{"px": str(price), "sz": str(size)} for price, size in asks],
            ]
        },
    )


def mid_event(sequence: int, exchange: str, mid: float) -> MarketEvent:
    return MarketEvent.build(
        sequence=sequence,
        exchange=exchange,
        symbol="BTC",
        kind=EventKind.MID,
        event_time_ns=sequence * 1_000_000,
        receive_time_ns=sequence * 1_000_000,
        payload={"mid": str(mid)},
    )


def test_scanner() -> dict[str, Any]:
    engine = CrossExchangeArbitrageEngine(min_edge_bps=5, fee_bps=1, max_quantity=2)
    engine.update(BookQuote("venue-a", "BTC", 99, 100, 3, 3, 1))
    candidates = engine.update_candidates(BookQuote("venue-b", "BTC", 101, 102, 4, 4, 2))
    result = next(x for x in candidates if x.buy_exchange == "venue-a" and x.sell_exchange == "venue-b")
    expected = oracle(100, 101, 2, 1)

    check("scanner.buy_price", 100, result.buy_price)
    check("scanner.sell_price", 101, result.sell_price)
    check("scanner.quantity", 2, result.quantity)
    check("scanner.gross_edge_bps", expected["gross_bps"], result.gross_edge_bps)
    check("scanner.expected_edge_bps", expected["expected_bps"], result.expected_edge_bps)
    check("scanner.estimated_profit", expected["scanner_profit"], result.estimated_profit)
    check("scanner.decision", "accepted", result.decision, result.decision == "accepted")
    return {"oracle": {k: str(v) for k, v in expected.items()}, "actual": asdict(result)}


def test_rejection() -> dict[str, Any]:
    engine = CrossExchangeArbitrageEngine(min_edge_bps=5, fee_bps=2, max_quantity=1)
    engine.update(BookQuote("buy", "BTC", 99, 100, 3, 0.8, 1))
    candidates = engine.update_candidates(BookQuote("sell", "BTC", 100.05, 101, 0.4, 2, 2))
    result = next(x for x in candidates if x.buy_exchange == "buy" and x.sell_exchange == "sell")
    expected = oracle(100, 100.05, 0.4, 2)

    check("rejection.gross_edge_bps", expected["gross_bps"], result.gross_edge_bps)
    check("rejection.expected_edge_bps", expected["expected_bps"], result.expected_edge_bps)
    check("rejection.decision", "rejected", result.decision, result.decision == "rejected")
    check("rejection.explanation", "explicit below-threshold reason", result.explanation, "below" in result.explanation.lower())
    return {"oracle": {k: str(v) for k, v in expected.items()}, "actual": asdict(result)}


def test_depth() -> dict[str, Any]:
    engine = CrossExchangeArbitrageEngine(min_edge_bps=0, fee_bps=2, max_quantity=2)
    engine.update(BookQuote("buy", "BTC", 99, 100, 2, 2, 1, ask_levels=((100, 0.5), (101, 1.5))))
    candidates = engine.update_candidates(
        BookQuote("sell", "BTC", 103, 104, 2, 2, 2, bid_levels=((103, 0.5), (102, 1.5)))
    )
    result = next(x for x in candidates if x.buy_exchange == "buy" and x.sell_exchange == "sell")
    buy_vwap = (D(100) * D("0.5") + D(101) * D("1.5")) / D(2)
    sell_vwap = (D(103) * D("0.5") + D(102) * D("1.5")) / D(2)

    check("depth.buy_vwap", buy_vwap, result.buy_price)
    check("depth.sell_vwap", sell_vwap, result.sell_price)
    return {"expected_buy_vwap": str(buy_vwap), "expected_sell_vwap": str(sell_vwap), "actual": asdict(result)}


def test_partial_fill() -> dict[str, Any]:
    snapshot = OrderBookSnapshot.from_payload(
        {"exchange": "venue", "symbol": "BTC", "timestamp_ms": 1000, "sequence": 1,
         "asks": [[100, 1], [101, 0.5]], "bids": [[99, 2]], "environment": "simulation"}
    )
    result = simulate_order(snapshot, Side.BUY, quantity=2, fee_bps=2)
    expected_notional = D(100) + D(101) * D("0.5")
    expected_vwap = expected_notional / D("1.5")
    expected_fee = expected_notional * D(2) / D(10_000)

    check("fill.status", OrderStatus.PARTIALLY_FILLED.value, result.status.value, result.status == OrderStatus.PARTIALLY_FILLED)
    check("fill.quantity", D("1.5"), result.filled_quantity)
    check("fill.remaining", D("0.5"), result.remaining_quantity)
    check("fill.vwap", expected_vwap, result.average_price)
    check("fill.fees", expected_fee, result.fees)
    return {"expected_vwap": str(expected_vwap), "expected_fee": str(expected_fee), "actual": {
        "status": result.status.value, "filled_quantity": result.filled_quantity,
        "remaining_quantity": result.remaining_quantity, "average_price": result.average_price,
        "fees": result.fees,
    }}


def test_replay() -> dict[str, Any]:
    events = [
        book_event(1, "venue-a", [(99, 3)], [(100, 3)]),
        book_event(2, "venue-b", [(101, 4)], [(102, 4)]),
        mid_event(3, "venue-a", 100.5),
        mid_event(4, "venue-b", 100.5),
    ]
    parameters = {"min_edge_bps": 5, "fee_bps": 1, "max_quantity": 2}
    engine = DeterministicReplayEngine(timer_interval_ms=1000, fee_bps=1)
    first = engine.run(events, make_strategy("cross_exchange_arbitrage", parameters))
    second = engine.run(events, make_strategy("cross_exchange_arbitrage", parameters))
    first_json = json.dumps(first.model_dump(), sort_keys=True, separators=(",", ":"))
    expected_equity = D(100_000) + oracle(100, 101, 2, 1)["exact_cash_pnl"]

    check("replay.deterministic", True, first.model_dump() == second.model_dump(), first.model_dump() == second.model_dump())
    check("replay.fill_count", 2, first.fill_count)
    check("replay.final_equity", expected_equity, first.final_equity)
    return {"expected_final_equity": str(expected_equity), "result_sha256": hashlib.sha256(first_json.encode()).hexdigest()}


def test_monte_carlo() -> dict[str, Any]:
    returns = [0.01, -0.02, 0.03, -0.005, 0.012]
    first = monte_carlo_resample(returns, runs=1000, block_size=2, seed=11)
    second = monte_carlo_resample(returns, runs=1000, block_size=2, seed=11)
    check("monte_carlo.seeded_reproducibility", True, first == second, first == second)
    return first


def source_hashes() -> dict[str, str]:
    paths = [
        BACKEND / "app" / "research" / "engine.py",
        BACKEND / "app" / "research" / "events.py",
        BACKEND / "app" / "research" / "orderbook.py",
    ]
    return {str(path.relative_to(BACKEND)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def main() -> int:
    evidence = {
        "scanner": test_scanner(),
        "rejection": test_rejection(),
        "depth": test_depth(),
        "partial_fill": test_partial_fill(),
        "replay": test_replay(),
        "monte_carlo": test_monte_carlo(),
    }
    failed = [item for item in checks if not item.passed]
    report = {
        "title": "QuantForge Calculation Accuracy Certificate",
        "method": "QuantForge results compared with independent Decimal known-answer calculations",
        "status": "PASS" if not failed else "FAIL",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed)},
        "source_sha256": source_hashes(),
        "tolerance": TOLERANCE,
        "checks": [asdict(item) for item in checks],
        "evidence": evidence,
        "scope": {
            "proves": "Calculation correctness and reproducibility for the included fixtures.",
            "does_not_prove": "Future profitability, live executability, or perfect exchange microstructure fidelity.",
        },
    }
    output = Path.cwd() / "quantforge-accuracy-certificate.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n")

    print("\nQuantForge Calculation Accuracy Certificate")
    print("=" * 46)
    for item in checks:
        print(f"[{'PASS' if item.passed else 'FAIL'}] {item.name}")
    print("-" * 46)
    print(f"{report['summary']['passed']}/{report['summary']['checks']} checks passed — {report['status']}")
    print(f"Evidence: {output}")
    print("Scope: calculation correctness and reproducibility, not predictive accuracy.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
