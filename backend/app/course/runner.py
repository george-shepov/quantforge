from __future__ import annotations

import asyncio
import hashlib
import os
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.engine import run_backtest
from app.exchanges.synthetic import SyntheticAdapter
from app.models import BacktestRequest
from app.research.engine import (
    DeterministicReplayEngine,
    make_strategy,
    monte_carlo_resample,
    parameter_combinations,
    walk_forward_windows,
)
from app.research.events import MarketEvent
from app.research.orderbook import OrderBookSnapshot, Side, simulate_order

from .delta import classify_deltas, compare_direction, compare_expectation, compare_expected_actual
from .fixture import COURSE_DATASET_ID, course_fixture_events, fixture_checksum_chain, course_fixture_manifest
from .renderers import render_platform_exports, render_research_report
from .schema import (
    CourseManifest,
    ExecutableScenario,
    build_evidence,
    default_manifest_path,
    load_manifest,
)


class CourseRunRequest(BaseModel):
    scenario_id: str = "qf-course-01-survive-reality"
    seed: int = 7
    git_sha: str | None = None


def _git_sha(explicit: str | None) -> str:
    if explicit:
        return explicit
    configured = os.getenv("QUANTFORGE_GIT_SHA")
    if configured:
        return configured
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).parents[3],
            capture_output=True,
            check=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _get_path(payload: dict[str, Any], path: str) -> Any:
    value: Any = payload
    for part in path.split("."):
        if part == "length":
            value = len(value)
        elif isinstance(value, dict):
            value = value[part]
        else:
            return None
    return value


class CourseScenarioRunner:
    def __init__(self, manifest_path: str | Path | None = None) -> None:
        self.manifest: CourseManifest = load_manifest(manifest_path or default_manifest_path())

    def run(self, request: CourseRunRequest | None = None) -> dict[str, Any]:
        request = request or CourseRunRequest()
        if request.scenario_id != self.manifest.module_id:
            raise ValueError(f"Unknown course scenario: {request.scenario_id}")
        git_sha = _git_sha(request.git_sha)
        labs: list[dict[str, Any]] = []
        previous_execution: dict[str, Any] | None = None
        for lab in self.manifest.labs:
            raw = {"lab_id": lab.lab_id, "title": lab.title, **(lab.model_extra or {})}
            if "expected_exact" in raw:
                execution = self._run_orderbook_lab(raw, previous_execution)
                previous_execution = execution
                labs.append(self._scenario_from_execution(lab.lab_id, raw, execution, request.seed, git_sha))
            elif lab.lab_id == "baseline-candle-backtest" or "endpoint" in raw and "backtests" in raw["endpoint"]:
                labs.append(self._run_backtest_lab(lab.lab_id, raw, request.seed, git_sha))
            elif lab.lab_id == "execution-friction-comparison":
                labs.append(self._run_friction_lab(lab.lab_id, raw, request.seed, git_sha))
            elif lab.lab_id == "walk-forward-window-evaluation":
                labs.append(self._run_experiment_lab(lab.lab_id, raw, request.seed, git_sha, monte_carlo_runs=0))
            elif lab.lab_id == "block-monte-carlo":
                labs.append(self._run_experiment_lab(lab.lab_id, raw, request.seed, git_sha, monte_carlo_runs=1000))
            else:
                labs.append(self._informational_lab(lab.lab_id, raw, request.seed, git_sha))
        result = {
            "scenario_id": self.manifest.module_id,
            "schema_version": self.manifest.schema_version,
            "title": self.manifest.title,
            "question": self.manifest.research_contract["question"],
            "hypothesis": self.manifest.research_contract["hypothesis"],
            "invalidation_conditions": self.manifest.research_contract["invalidation_conditions"],
            "labs": labs,
            "fixture": course_fixture_manifest(),
            "provenance": {
                "scenario_version": self.manifest.schema_version,
                "quantforge_git_sha": git_sha,
                "dataset_id": COURSE_DATASET_ID,
                "dataset_checksum_chain": fixture_checksum_chain(),
                "random_seed": request.seed,
                "evidence_ids": [self._evidence_id(lab) for lab in labs],
            },
            "verdict": self._verdict(labs),
        }
        result["exports"] = render_platform_exports(result)
        result["research_report"] = render_research_report(result)
        return result

    @staticmethod
    def _evidence_id(lab: dict[str, Any]) -> str:
        return hashlib.sha256(
            f"{lab['scenario_id']}:{json_dumps_stable(lab.get('actual_outcome', {}))}".encode()
        ).hexdigest()[:16]

    @staticmethod
    def _verdict(labs: list[dict[str, Any]]) -> str:
        classifications = {lab.get("delta_classification") for lab in labs}
        if "data_quality_warning" in classifications or "assumption_failure" in classifications:
            return "revise"
        return "continue_research"

    def _scenario_from_execution(
        self,
        lab_id: str,
        raw: dict[str, Any],
        execution: dict[str, Any],
        seed: int,
        git_sha: str,
    ) -> dict[str, Any]:
        expected = raw["expected_exact"]
        actual = {"execution": {key: value for key, value in execution.items() if key != "_request"}}
        deltas = [
            compare_expected_actual(path, expected_value, _get_path(actual, path), tolerance=raw.get("tolerance", 1e-9))
            for path, expected_value in expected.items()
        ]
        scenario = ExecutableScenario(
            scenario_id=lab_id,
            schema_version=self.manifest.schema_version,
            parameter_set={
                "side": (raw.get("request") or {}).get("side", "buy"),
                "quantity": (raw.get("request") or {}).get("quantity", 1.0),
                "limit_price": (raw.get("patch") or {}).get("limit_price"),
            },
            purpose=raw["title"],
            question=raw.get("request", {}).get("intent", raw["title"]),
            hypothesis=raw.get("request", {}).get("hypothesis", "The expected execution should match the recorded book."),
            assumptions=raw.get("request", {}).get("assumptions", ["The fixture is synthetic and deterministic."]),
            expected_outcome=expected,
            actual_outcome=actual,
            delta=deltas,
            why_delta_occurred="The deterministic order-book replay applies each eligible level in price order.",
            delta_classification=classify_deltas(deltas),
            validation_steps=[
                "Sum fill quantities and compare with filled_quantity.",
                "Recalculate notional divided by filled quantity.",
                "Compare requested, filled, and remaining quantities.",
            ],
            risk_and_invalidation_conditions=raw.get("request", {}).get(
                "invalidation_conditions", self.manifest.research_contract["invalidation_conditions"]
            ),
            evidence=build_evidence(
                scenario_version=self.manifest.schema_version,
                dataset_id=COURSE_DATASET_ID,
                dataset_checksum_chain=fixture_checksum_chain(),
                random_seed=seed,
                evidence_ids=[lab_id],
                quantforge_git_sha=git_sha,
            ),
        )
        return scenario.model_dump(mode="json")

    def _run_orderbook_lab(
        self, raw: dict[str, Any], previous_execution: dict[str, Any] | None
    ) -> dict[str, Any]:
        request = deepcopy(raw.get("request") or {})
        if not request and previous_execution:
            request = deepcopy(previous_execution["_request"])
        request.update(raw.get("patch") or {})
        snapshot = OrderBookSnapshot.from_payload(request["snapshot"])
        result = simulate_order(snapshot, Side(request["side"]), request["quantity"], request.get("limit_price"))
        execution = {
            "requested_quantity": result.requested_quantity,
            "filled_quantity": result.filled_quantity,
            "remaining_quantity": result.remaining_quantity,
            "average_price": result.average_price,
            "status": result.status.value,
            "fills": [{"price": fill.price, "quantity": fill.quantity, "notional": fill.notional} for fill in result.fills],
        }
        execution["_request"] = request
        return execution

    def _run_backtest_lab(self, lab_id: str, raw: dict[str, Any], seed: int, git_sha: str) -> dict[str, Any]:
        request = BacktestRequest.model_validate(raw["request"])
        candles = asyncio.run(SyntheticAdapter().fetch_candles(request.market))
        response = asyncio.run(run_backtest(request, candles, "synthetic-course-fixture", []))
        actual = response.model_dump(mode="json")
        metrics = actual["metrics"]
        expectations = raw.get("expectations", [])
        deltas = [
            compare_expectation(
                item["metric"],
                item,
                _get_path(actual, item["metric"]),
            )
            for item in expectations
        ]
        return self._generic_scenario(
            lab_id, raw, {"request": request.model_dump(mode="json")}, metrics, deltas, seed, git_sha
        )

    def _run_friction_lab(self, lab_id: str, raw: dict[str, Any], seed: int, git_sha: str) -> dict[str, Any]:
        baseline = next(
            {"request": deepcopy((lab.model_extra or {}).get("request", {}))}
            for lab in self.manifest.labs
            if lab.lab_id == "baseline-candle-backtest"
        )
        variants: dict[str, Any] = {}
        for variant in raw.get("variants", []):
            request_data = deepcopy(baseline["request"])
            for path, value in variant.get("patch", {}).items():
                section, field = path.split(".", 1)
                request_data[section][field] = value
            request = BacktestRequest.model_validate(request_data)
            candles = asyncio.run(SyntheticAdapter().fetch_candles(request.market))
            response = asyncio.run(run_backtest(request, candles, "synthetic-course-fixture", []))
            variants[variant["variant_id"]] = response.model_dump(mode="json")["metrics"]
        actual = {"variants": variants}
        baseline_request = BacktestRequest.model_validate(baseline["request"])
        baseline_candles = asyncio.run(SyntheticAdapter().fetch_candles(baseline_request.market))
        baseline_metrics = asyncio.run(
            run_backtest(baseline_request, baseline_candles, "synthetic-course-fixture", [])
        ).model_dump(mode="json")["metrics"]
        deltas = []
        for variant in raw.get("variants", []):
            variant_metrics = variants[variant["variant_id"]]
            for metric, direction in variant.get("expected_direction", {}).items():
                metric_name = metric.removeprefix("metrics.")
                deltas.append(
                    compare_direction(
                        f"{variant['variant_id']}.{metric}",
                        direction,
                        baseline_metrics.get(metric_name),
                        variant_metrics.get(metric_name),
                    )
                )
        return self._generic_scenario(
            lab_id,
            raw,
            {"variants": variants},
            actual,
            deltas,
            seed,
            git_sha,
            expected_outcome={
                f"{variant['variant_id']}.{metric}": direction
                for variant in raw.get("variants", [])
                for metric, direction in variant.get("expected_direction", {}).items()
            },
        )

    def _run_experiment_lab(
        self, lab_id: str, raw: dict[str, Any], seed: int, git_sha: str, *, monte_carlo_runs: int
    ) -> dict[str, Any]:
        request = deepcopy(raw.get("request") or self._walk_forward_request())
        request.update(raw.get("patch") or {})
        request["seed"] = seed
        request["monte_carlo_runs"] = monte_carlo_runs
        events = course_fixture_events()
        windows = walk_forward_windows(len(events), request["walk_forward_folds"])
        candidates: list[dict[str, Any]] = []
        for parameters in parameter_combinations(request["base_parameters"], request["parameter_grid"]):
            folds = []
            returns = []
            for fold_index, (_, test_slice) in enumerate(windows):
                replay = DeterministicReplayEngine(request["timer_interval_ms"]).run(
                    events[test_slice], make_strategy(request["strategy"], parameters), request["starting_cash"]
                )
                returns.append(replay.return_pct / 100)
                folds.append(
                    {
                        "fold": fold_index,
                        "event_count": replay.event_count,
                        "return_pct": replay.return_pct,
                        "max_drawdown_pct": replay.max_drawdown_pct,
                        "fill_count": replay.fill_count,
                    }
                )
            score = sum(returns) / len(returns) if returns else -1e100
            candidates.append(
                {
                    "parameters": parameters,
                    "score": score,
                    "folds": folds,
                    "monte_carlo": monte_carlo_resample(
                        returns, runs=monte_carlo_runs, block_size=request["monte_carlo_block_size"], seed=seed
                    ),
                }
            )
        candidates.sort(key=lambda candidate: candidate["score"], reverse=True)
        actual = {"dataset_id": COURSE_DATASET_ID, "candidate_count": len(candidates), "best": candidates[0], "candidates": candidates}
        return self._generic_scenario(lab_id, raw, request, actual, [], seed, git_sha)

    def _walk_forward_request(self) -> dict[str, Any]:
        for lab in self.manifest.labs:
            if lab.lab_id == "walk-forward-window-evaluation":
                return deepcopy((lab.model_extra or {}).get("request", {}))
        raise ValueError("The manifest does not define a walk-forward request")

    def _generic_scenario(
        self,
        lab_id: str,
        raw: dict[str, Any],
        parameters: dict[str, Any],
        actual: dict[str, Any],
        deltas: list[Any],
        seed: int,
        git_sha: str,
        expected_outcome: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        scenario = ExecutableScenario(
            scenario_id=lab_id,
            schema_version=self.manifest.schema_version,
            parameter_set=parameters,
            purpose=raw["title"],
            question=raw.get("request", {}).get("intent", raw["title"]),
            hypothesis=raw.get("request", {}).get("hypothesis", raw["title"]),
            assumptions=raw.get("request", {}).get("assumptions", ["The deterministic course fixture is synthetic."]),
            expected_outcome=expected_outcome
            or raw.get("expected_exact", {item["metric"]: item.get("value") for item in raw.get("expectations", [])}),
            actual_outcome=actual,
            delta=deltas,
            why_delta_occurred="The runner measured this lab from the executable request and deterministic evidence.",
            delta_classification=classify_deltas(deltas) if deltas else "matched",
            validation_steps=["Inspect the generated actual values.", "Repeat the run with the same seed.", "Review the evidence provenance."],
            risk_and_invalidation_conditions=raw.get("request", {}).get("invalidation_conditions", self.manifest.research_contract["invalidation_conditions"]),
            evidence=build_evidence(
                scenario_version=self.manifest.schema_version,
                dataset_id=COURSE_DATASET_ID,
                dataset_checksum_chain=fixture_checksum_chain(),
                random_seed=seed,
                evidence_ids=[lab_id],
                quantforge_git_sha=git_sha,
            ),
        )
        return scenario.model_dump(mode="json")

    def _informational_lab(self, lab_id: str, raw: dict[str, Any], seed: int, git_sha: str) -> dict[str, Any]:
        return self._generic_scenario(lab_id, raw, {}, {"status": "declared"}, [], seed, git_sha)


def json_dumps_stable(value: Any) -> str:
    import json

    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
