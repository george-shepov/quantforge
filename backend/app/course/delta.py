from __future__ import annotations

import math
from typing import Any

from .schema import DeltaClassification, ScenarioMeasurement


def _numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _status(value: Any) -> str:
    return "partial" if value == "partially_filled" else str(value)


def compare_expected_actual(
    metric: str,
    expected: Any,
    actual: Any,
    *,
    tolerance: float = 1e-9,
    explanation: str = "",
) -> ScenarioMeasurement:
    absolute: float | None = None
    percentage: float | None = None
    if _numeric(expected) and _numeric(actual):
        absolute = float(actual) - float(expected)
        percentage = None if float(expected) == 0 else absolute / abs(float(expected)) * 100
        classification = (
            DeltaClassification.MATCHED
            if abs(absolute) <= tolerance
            else DeltaClassification.EXPLAINABLE_DEVIATION
        )
    elif _status(expected) == _status(actual):
        classification = DeltaClassification.MATCHED
    elif expected == "record_only":
        classification = DeltaClassification.MATCHED
    elif expected is None or actual is None:
        classification = DeltaClassification.DATA_QUALITY_WARNING
    else:
        classification = DeltaClassification.ASSUMPTION_FAILURE
    return ScenarioMeasurement(
        metric=metric,
        expected=expected,
        actual=actual,
        absolute_delta=absolute,
        percentage_delta=percentage,
        classification=classification,
        explanation=explanation,
    )


def compare_expectation(
    metric: str,
    expectation: dict[str, Any],
    actual: Any,
    *,
    tolerance: float = 1e-9,
) -> ScenarioMeasurement:
    kind = expectation.get("kind")
    expected = expectation.get("value")
    if kind in {"minimum", "greater_than"} and _numeric(actual) and _numeric(expected):
        satisfied = actual >= expected if kind == "minimum" else actual > expected
        classification = DeltaClassification.MATCHED if satisfied else DeltaClassification.EXPLAINABLE_DEVIATION
        absolute = float(actual) - float(expected)
        percentage = None if float(expected) == 0 else absolute / abs(float(expected)) * 100
        return ScenarioMeasurement(
            metric=metric,
            expected=expected,
            actual=actual,
            absolute_delta=absolute,
            percentage_delta=percentage,
            classification=classification,
            explanation=expectation.get("reason", ""),
        )
    return compare_expected_actual(
        metric,
        expected,
        actual,
        tolerance=tolerance,
        explanation=expectation.get("reason", ""),
    )


def compare_direction(
    metric: str,
    direction: str,
    baseline: Any,
    actual: Any,
) -> ScenarioMeasurement:
    if direction == "increase":
        satisfied = _numeric(baseline) and _numeric(actual) and actual > baseline
    elif direction.startswith("not_increase"):
        satisfied = _numeric(baseline) and _numeric(actual) and actual <= baseline
    elif direction == "decrease":
        satisfied = _numeric(baseline) and _numeric(actual) and actual < baseline
    else:
        satisfied = True
    classification = (
        DeltaClassification.MATCHED
        if satisfied
        else DeltaClassification.EXPLAINABLE_DEVIATION
    )
    absolute = float(actual) - float(baseline) if _numeric(actual) and _numeric(baseline) else None
    percentage = (
        None
        if absolute is None or float(baseline) == 0
        else absolute / abs(float(baseline)) * 100
    )
    return ScenarioMeasurement(
        metric=metric,
        expected=direction,
        actual=actual,
        absolute_delta=absolute,
        percentage_delta=percentage,
        classification=classification,
        explanation=f"Compared with the baseline value {baseline}.",
    )


def classify_deltas(deltas: list[ScenarioMeasurement]) -> DeltaClassification:
    if any(item.classification == DeltaClassification.DATA_QUALITY_WARNING for item in deltas):
        return DeltaClassification.DATA_QUALITY_WARNING
    if any(item.classification == DeltaClassification.ASSUMPTION_FAILURE for item in deltas):
        return DeltaClassification.ASSUMPTION_FAILURE
    if any(item.classification == DeltaClassification.EXPLAINABLE_DEVIATION for item in deltas):
        return DeltaClassification.EXPLAINABLE_DEVIATION
    return DeltaClassification.MATCHED
