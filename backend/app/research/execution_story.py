from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Iterable

from app.research.orderbook import ExecutionResult, OrderBookSnapshot, Side


class EvidenceKind(str, Enum):
    FACT = "fact"
    ASSUMPTION = "assumption"
    HYPOTHESIS = "hypothesis"
    RESULT = "result"
    RISK = "risk"


class StoryMode(str, Enum):
    EXPERT = "expert"
    GUIDED = "guided"


@dataclass(frozen=True)
class EvidenceItem:
    kind: EvidenceKind
    label: str
    value: str
    explanation: str | None = None


@dataclass(frozen=True)
class ValidationStep:
    label: str
    instruction: str
    expected: str


@dataclass
class ExecutionStory:
    title: str
    intent: str
    hypothesis: str
    assumptions: list[str] = field(default_factory=list)
    invalidation_conditions: list[str] = field(default_factory=list)
    hopes: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    evidence: list[EvidenceItem] = field(default_factory=list)
    validation_steps: list[ValidationStep] = field(default_factory=list)
    reflection_prompt: str = "What happened, why, and what would you change next?"
    post_run_reflection: str = ""

    def render(self, mode: StoryMode) -> dict:
        base = {
            "title": self.title,
            "intent": self.intent,
            "hypothesis": self.hypothesis,
            "evidence": [asdict(item) for item in self.evidence],
            "export": self.export(),
        }
        if mode == StoryMode.EXPERT:
            return {
                **base,
                "mode": mode.value,
                "summary": self._expert_summary(),
                "detailsCollapsed": True,
            }
        return {
            **base,
            "mode": mode.value,
            "summary": self._guided_summary(),
            "assumptions": self.assumptions,
            "invalidationConditions": self.invalidation_conditions,
            "hopes": self.hopes,
            "risks": self.risks,
            "validationSteps": [asdict(step) for step in self.validation_steps],
            "reflectionPrompt": self.reflection_prompt,
            "postRunReflection": self.post_run_reflection,
            "detailsCollapsed": False,
        }

    def export(self) -> dict:
        return {
            "title": self.title,
            "intent": self.intent,
            "hypothesis": self.hypothesis,
            "assumptions": self.assumptions,
            "invalidationConditions": self.invalidation_conditions,
            "hopes": self.hopes,
            "risks": self.risks,
            "evidence": [asdict(item) for item in self.evidence],
            "validationSteps": [asdict(step) for step in self.validation_steps],
            "reflectionPrompt": self.reflection_prompt,
            "postRunReflection": self.post_run_reflection,
        }

    def _expert_summary(self) -> str:
        result = next((item.value for item in self.evidence if item.kind == EvidenceKind.RESULT), None)
        return result or self.hypothesis

    def _guided_summary(self) -> str:
        result = next((item for item in self.evidence if item.kind == EvidenceKind.RESULT), None)
        if result and result.explanation:
            return result.explanation
        return result.value if result else self.hypothesis


def build_execution_story(
    snapshot: OrderBookSnapshot,
    side: Side,
    result: ExecutionResult,
    *,
    intent: str,
    hypothesis: str,
    assumptions: Iterable[str] = (),
    invalidation_conditions: Iterable[str] = (),
    hopes: Iterable[str] = (),
    risks: Iterable[str] = (),
    post_run_reflection: str = "",
) -> ExecutionStory:
    assumptions = list(assumptions)
    invalidation_conditions = list(invalidation_conditions)
    hopes = list(hopes)
    risks = list(risks)
    fill_pct = 0.0
    if result.requested_quantity > 0:
        fill_pct = 100.0 * result.filled_quantity / result.requested_quantity

    average = "not filled" if result.average_price is None else f"{result.average_price:.8g}"
    result_text = (
        f"{result.status.value}: filled {result.filled_quantity:.8g} of "
        f"{result.requested_quantity:.8g} ({fill_pct:.2f}%) at average {average}"
    )
    explanation = _plain_language_result(side, result, snapshot)

    evidence = [
        EvidenceItem(EvidenceKind.FACT, "Exchange", snapshot.exchange),
        EvidenceItem(EvidenceKind.FACT, "Environment", snapshot.environment),
        EvidenceItem(EvidenceKind.FACT, "Book timestamp", str(snapshot.timestamp_ms)),
        EvidenceItem(EvidenceKind.FACT, "Book sequence", str(snapshot.sequence)),
        EvidenceItem(EvidenceKind.HYPOTHESIS, "Expected outcome", hypothesis),
        EvidenceItem(EvidenceKind.RESULT, "Execution result", result_text, explanation),
        EvidenceItem(EvidenceKind.FACT, "Filled notional", f"{result.notional:.8g}"),
        EvidenceItem(EvidenceKind.FACT, "Execution fees", f"{result.fees:.8g}"),
    ]
    evidence.extend(EvidenceItem(EvidenceKind.ASSUMPTION, "Assumption", item) for item in assumptions)
    evidence.extend(EvidenceItem(EvidenceKind.RISK, "Risk", item) for item in risks)

    return ExecutionStory(
        title=f"{side.value.title()} {snapshot.symbol} on {snapshot.exchange}",
        intent=intent,
        hypothesis=hypothesis,
        assumptions=list(assumptions),
        invalidation_conditions=list(invalidation_conditions),
        hopes=list(hopes),
        risks=list(risks),
        evidence=evidence,
        validation_steps=[
            ValidationStep(
                "Inspect the book",
                "Compare the requested quantity with each eligible price level in order.",
                "The sum of fill quantities equals the reported filled quantity.",
            ),
            ValidationStep(
                "Recalculate average price",
                "Add each fill's price multiplied by quantity, then divide by total filled quantity.",
                "The result matches the reported average execution price.",
            ),
            ValidationStep(
                "Check remaining exposure",
                "Subtract filled quantity from requested quantity.",
                "The result matches remaining quantity and the order status.",
            ),
        ],
        post_run_reflection=post_run_reflection,
    )


def _plain_language_result(side: Side, result: ExecutionResult, snapshot: OrderBookSnapshot) -> str:
    if result.filled_quantity <= 0:
        return (
            f"The {side.value} order did not execute against the recorded {snapshot.exchange} book. "
            "That may mean the limit price did not cross available liquidity or the book had no usable depth."
        )
    if result.remaining_quantity > 0:
        return (
            f"The order consumed all eligible liquidity available in this snapshot, but only part of the requested "
            f"quantity executed. The remaining {result.remaining_quantity:.8g} stayed unfilled, leaving execution risk."
        )
    if len(result.fills) > 1:
        return (
            "The order filled completely by consuming more than one price level. The average price therefore differs "
            "from the best displayed price; this is book-walking slippage."
        )
    return "The order filled completely at one recorded price level in the simulated book."


class ExecutionRunStore:
    """Persist execution facts and their explanatory story as one immutable export."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or os.getenv("QUANTFORGE_DATA_ROOT", "./data/quantforge")) / "execution-runs"
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, run_id: str, payload: dict) -> dict:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", run_id):
            raise ValueError("Invalid execution run ID")
        target = self.root / f"{run_id}.json"
        if target.exists():
            raise FileExistsError(run_id)
        payload = {
            **payload,
            "created_at": payload.get("created_at", datetime.now(timezone.utc).isoformat()),
        }
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        temporary.replace(target)
        return payload

    def get(self, run_id: str) -> dict:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", run_id):
            raise FileNotFoundError(run_id)
        target = self.root / f"{run_id}.json"
        if not target.exists():
            raise FileNotFoundError(run_id)
        return json.loads(target.read_text())

    def list(self, limit: int = 25) -> list[dict]:
        safe_limit = max(1, min(limit, 100))
        records: list[dict] = []
        for path in self.root.glob("*.json"):
            try:
                records.append(json.loads(path.read_text()))
            except (OSError, TypeError, ValueError):
                continue
        return sorted(records, key=lambda item: item.get("created_at", ""), reverse=True)[:safe_limit]


ExecutionStoryStore = ExecutionRunStore
