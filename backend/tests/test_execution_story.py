import pytest

from app.research.execution_story import EvidenceKind, ExecutionRunStore, StoryMode, build_execution_story
from app.research.orderbook import OrderBookSnapshot, OrderStatus, Side, simulate_order


def snapshot(*, asks=(), bids=(), exchange="bybit", environment="testnet"):
    return OrderBookSnapshot.from_payload(
        {
            "exchange": exchange,
            "symbol": "BTC",
            "timestamp_ms": 1234,
            "sequence": 7,
            "asks": asks,
            "bids": bids,
            "environment": environment,
        }
    )


def story_for(result, book, side=Side.BUY):
    return build_execution_story(
        book,
        side,
        result,
        intent="Learn whether available depth can fill the order.",
        hypothesis="The order should fill without material slippage.",
        assumptions=["The snapshot is fresh", "Fees are modeled separately"],
        invalidation_conditions=["Book age exceeds 500 ms"],
        hopes=["The strategy remains profitable after execution costs"],
        risks=["Partial fill creates residual exposure"],
    )


def test_guided_story_explains_partial_fill_and_validation():
    book = snapshot(asks=[[100, 0.4], [101, 0.3]])
    result = simulate_order(book, Side.BUY, 1.0)
    rendered = story_for(result, book).render(StoryMode.GUIDED)

    assert result.status == OrderStatus.PARTIALLY_FILLED
    assert rendered["mode"] == "guided"
    assert rendered["detailsCollapsed"] is False
    assert "remaining" in rendered["summary"].lower()
    assert len(rendered["validationSteps"]) == 3
    assert rendered["assumptions"] == ["The snapshot is fresh", "Fees are modeled separately"]
    assert rendered["risks"] == ["Partial fill creates residual exposure"]


def test_expert_story_stays_compact_but_preserves_same_evidence():
    book = snapshot(asks=[[100, 2]])
    result = simulate_order(book, Side.BUY, 1.0)
    story = story_for(result, book)

    guided = story.render(StoryMode.GUIDED)
    expert = story.render(StoryMode.EXPERT)

    assert expert["detailsCollapsed"] is True
    assert "validationSteps" not in expert
    assert expert["evidence"] == guided["evidence"]
    assert "filled" in expert["summary"]


def test_story_labels_fact_assumption_hypothesis_result_and_risk():
    book = snapshot(asks=[[100, 1]])
    result = simulate_order(book, Side.BUY, 1.0)
    story = story_for(result, book)

    kinds = {item.kind for item in story.evidence}
    assert EvidenceKind.FACT in kinds
    assert EvidenceKind.ASSUMPTION in kinds
    assert EvidenceKind.HYPOTHESIS in kinds
    assert EvidenceKind.RESULT in kinds
    assert EvidenceKind.RISK in kinds


def test_story_explains_multi_level_book_walking():
    book = snapshot(asks=[[100, 0.5], [102, 0.5]])
    result = simulate_order(book, Side.BUY, 1.0)
    rendered = story_for(result, book).render(StoryMode.GUIDED)

    assert result.status == OrderStatus.FILLED
    assert result.average_price == 101
    assert "more than one price level" in rendered["summary"].lower()
    assert "slippage" in rendered["summary"].lower()


def test_story_explains_unfilled_limit_order():
    book = snapshot(asks=[[101, 1]])
    result = simulate_order(book, Side.BUY, 1.0, limit_price=100)
    rendered = story_for(result, book).render(StoryMode.GUIDED)

    assert result.status == OrderStatus.OPEN
    assert "did not execute" in rendered["summary"].lower()
    assert "limit price" in rendered["summary"].lower()


def test_sell_story_uses_bid_liquidity():
    book = snapshot(bids=[[100, 0.25], [99, 0.75]])
    result = simulate_order(book, Side.SELL, 1.0)
    rendered = story_for(result, book, Side.SELL).render(StoryMode.GUIDED)

    assert result.status == OrderStatus.FILLED
    assert result.average_price == 99.25
    assert rendered["title"].startswith("Sell BTC")


def test_story_materializes_iterables_and_exports_reflection():
    book = snapshot(asks=[[100, 1]])
    result = simulate_order(book, Side.BUY, 1.0, fee_bps=10)
    story = build_execution_story(
        book,
        Side.BUY,
        result,
        intent="Test",
        hypothesis="It fills",
        assumptions=(item for item in ["Fresh book"]),
        risks=(item for item in ["Fees"]),
        post_run_reflection="The measured fill matched the hypothesis.",
    )

    rendered = story.render(StoryMode.GUIDED)
    assert rendered["assumptions"] == ["Fresh book"]
    assert rendered["risks"] == ["Fees"]
    assert rendered["postRunReflection"].startswith("The measured")
    assert rendered["export"]["postRunReflection"] == rendered["postRunReflection"]


def test_execution_run_store_persists_immutable_exports(tmp_path):
    store = ExecutionRunStore(tmp_path)
    payload = {"run_id": "run-1", "execution": {"status": "filled"}}

    stored = store.save("run-1", payload)

    assert store.get("run-1")["execution"]["status"] == "filled"
    assert stored["created_at"]
    with pytest.raises(FileExistsError):
        store.save("run-1", payload)
