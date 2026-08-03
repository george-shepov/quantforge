from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


SCHEMA_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


class DeltaClassification(str, Enum):
    MATCHED = "matched"
    EXPLAINABLE_DEVIATION = "explainable_deviation"
    ASSUMPTION_FAILURE = "assumption_failure"
    DATA_QUALITY_WARNING = "data_quality_warning"


class ScenarioEvidence(BaseModel):
    model_config = ConfigDict(extra="allow")

    scenario_version: str
    quantforge_git_sha: str
    dataset_id: str
    dataset_checksum_chain: str
    random_seed: int
    evidence_ids: list[str] = Field(default_factory=list)


class ScenarioMeasurement(BaseModel):
    metric: str
    expected: Any
    actual: Any
    absolute_delta: float | None = None
    percentage_delta: float | None = None
    classification: DeltaClassification
    explanation: str = ""


class ExecutableScenario(BaseModel):
    """The canonical, evidence-bearing unit rendered into every course product."""

    model_config = ConfigDict(extra="allow")

    scenario_id: str
    schema_version: str
    parameter_set: dict[str, Any]
    purpose: str
    question: str
    hypothesis: str
    assumptions: list[str] = Field(min_length=1)
    expected_outcome: dict[str, Any]
    actual_outcome: dict[str, Any] = Field(default_factory=dict)
    delta: list[ScenarioMeasurement] = Field(default_factory=list)
    why_delta_occurred: str = ""
    delta_classification: DeltaClassification = DeltaClassification.DATA_QUALITY_WARNING
    validation_steps: list[str] = Field(min_length=1)
    risk_and_invalidation_conditions: list[str] = Field(min_length=1)
    evidence: ScenarioEvidence

    @field_validator("schema_version")
    @classmethod
    def valid_schema_version(cls, value: str) -> str:
        if not SCHEMA_VERSION_RE.fullmatch(value):
            raise ValueError("schema_version must use MAJOR.MINOR.PATCH format")
        return value


class CourseLab(BaseModel):
    model_config = ConfigDict(extra="allow")

    lab_id: str
    title: str


class CourseManifest(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: str
    module_id: str
    title: str
    course_title: str
    labs: list[CourseLab] = Field(min_length=1)
    research_contract: dict[str, Any]
    safety: dict[str, Any]
    delta_classifications: list[dict[str, str]] = Field(min_length=4)

    @field_validator("schema_version")
    @classmethod
    def valid_schema_version(cls, value: str) -> str:
        if not SCHEMA_VERSION_RE.fullmatch(value):
            raise ValueError("schema_version must use MAJOR.MINOR.PATCH format")
        return value

    @field_validator("labs")
    @classmethod
    def unique_lab_ids(cls, value: list[CourseLab]) -> list[CourseLab]:
        ids = [lab.lab_id for lab in value]
        if len(ids) != len(set(ids)):
            raise ValueError("labs must have unique lab_id values")
        return value


def validate_manifest(payload: dict[str, Any]) -> CourseManifest:
    manifest = CourseManifest.model_validate(payload)
    required_contract = {"question", "hypothesis", "assumptions", "invalidation_conditions"}
    missing_contract = required_contract - manifest.research_contract.keys()
    if missing_contract:
        raise ValueError(f"research_contract is missing: {', '.join(sorted(missing_contract))}")
    if manifest.safety.get("mainnet_order_submission") is not False:
        raise ValueError("course scenarios must disable mainnet order submission")
    classifications = {item.get("id") for item in manifest.delta_classifications}
    expected = {item.value for item in DeltaClassification}
    if not expected.issubset(classifications):
        raise ValueError("manifest must define all delta classifications")
    return manifest


def load_manifest(path: str | Path | None = None) -> CourseManifest:
    manifest_path = Path(path) if path else default_manifest_path()
    return validate_manifest(json.loads(manifest_path.read_text(encoding="utf-8")))


def default_manifest_path() -> Path:
    configured = os.getenv("QUANTFORGE_COURSE_MANIFEST")
    if configured:
        return Path(configured)
    relative = Path("course/modules/01-can-this-strategy-survive-reality.json")
    candidates = (Path(__file__).parents[3] / relative, Path.cwd() / relative)
    return next((path for path in candidates if path.exists()), candidates[0])


def build_evidence(
    *,
    scenario_version: str,
    dataset_id: str,
    dataset_checksum_chain: str,
    random_seed: int,
    evidence_ids: list[str],
    quantforge_git_sha: str | None = None,
) -> ScenarioEvidence:
    return ScenarioEvidence(
        scenario_version=scenario_version,
        quantforge_git_sha=quantforge_git_sha or "unknown",
        dataset_id=dataset_id,
        dataset_checksum_chain=dataset_checksum_chain,
        random_seed=random_seed,
        evidence_ids=evidence_ids,
    )


def generated_at() -> str:
    return datetime.now(timezone.utc).isoformat()
