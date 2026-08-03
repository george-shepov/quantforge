from __future__ import annotations

import json
from pathlib import Path

from app.course.delta import DeltaClassification, compare_expected_actual
from app.course.fixture import COURSE_DATASET_ID, course_fixture_events, fixture_checksum_chain, fixture_json
from app.course.runner import CourseScenarioRunner
from app.course.schema import load_manifest, validate_manifest
from app.main import app
from app.research.orderbook import OrderBookSnapshot, Side, simulate_order
from fastapi.testclient import TestClient


def test_starter_manifest_is_versioned_and_safe():
    manifest = load_manifest()

    assert manifest.schema_version == "0.1.0"
    assert manifest.module_id == "qf-course-01-survive-reality"
    assert manifest.safety["mainnet_order_submission"] is False
    assert {item["id"] for item in manifest.delta_classifications} == {
        "matched",
        "explainable_deviation",
        "assumption_failure",
        "data_quality_warning",
    }


def test_manifest_validator_rejects_mainnet_course_scenarios():
    payload = load_manifest().model_dump(mode="json")
    payload["safety"]["mainnet_order_submission"] = True

    try:
        validate_manifest(payload)
    except ValueError as exc:
        assert "mainnet" in str(exc)
    else:
        raise AssertionError("Unsafe course manifests must be rejected")


def test_course_fixture_is_deterministic_and_provenance_ready():
    first = course_fixture_events()
    second = course_fixture_events()

    assert [event.checksum for event in first] == [event.checksum for event in second]
    assert len(first) == 32
    assert fixture_checksum_chain(first) == fixture_checksum_chain(second)
    assert COURSE_DATASET_ID == "course-btc-l2-v1"
    assert [event.event_time_ns for event in first] == sorted(event.event_time_ns for event in first)


def test_checked_in_course_fixture_matches_the_generator():
    fixture_path = Path(__file__).parents[2] / "course/fixtures/course-btc-l2-v1.json"

    assert json.loads(fixture_path.read_text(encoding="utf-8")) == json.loads(fixture_json())


def test_expected_actual_delta_calculates_absolute_and_percentage_values():
    delta = compare_expected_actual("fill", 1.0, 0.75)

    assert delta.classification == DeltaClassification.EXPLAINABLE_DEVIATION
    assert delta.absolute_delta == -0.25
    assert delta.percentage_delta == -25.0


def test_starter_l2_market_fill_golden_example():
    snapshot = OrderBookSnapshot.from_payload(
        {
            "exchange": "course_fixture",
            "symbol": "BTC",
            "timestamp_ms": 1770000000000,
            "sequence": 1,
            "bids": [[100.0, 0.3], [99.5, 0.7], [99.0, 1.0]],
            "asks": [[100.5, 0.25], [101.0, 0.5], [102.0, 1.25]],
        }
    )
    result = simulate_order(snapshot, Side.BUY, 1.0)

    assert result.filled_quantity == 1.0
    assert result.remaining_quantity == 0.0
    assert result.average_price == 101.125
    assert len(result.fills) == 3


def test_starter_l2_limit_partial_fill_golden_example():
    snapshot = OrderBookSnapshot.from_payload(
        {
            "exchange": "course_fixture",
            "symbol": "BTC",
            "timestamp_ms": 1770000000000,
            "sequence": 1,
            "bids": [[100.0, 0.3], [99.5, 0.7], [99.0, 1.0]],
            "asks": [[100.5, 0.25], [101.0, 0.5], [102.0, 1.25]],
        }
    )
    result = simulate_order(snapshot, Side.BUY, 1.0, limit_price=101.0)

    assert result.filled_quantity == 0.75
    assert result.remaining_quantity == 0.25
    assert result.average_price == 100.83333333333333
    assert result.status.value == "partially_filled"


def test_runner_renders_all_products_from_one_deterministic_evidence_set():
    runner = CourseScenarioRunner()
    first = runner.run()
    second = runner.run()

    assert [lab["actual_outcome"] for lab in first["labs"]] == [lab["actual_outcome"] for lab in second["labs"]]
    assert set(first["exports"]) == {
        "guided",
        "expert",
        "instructor",
        "workbook",
        "kdp",
        "quiz",
        "youtube",
        "udemy",
        "pluralsight",
        "linkedin_learning",
        "marketing",
    }
    assert len(first["labs"]) == 6
    assert first["provenance"]["dataset_id"] == COURSE_DATASET_ID
    assert first["provenance"]["dataset_checksum_chain"] == fixture_checksum_chain()
    assert "101.125" in first["research_report"]
    assert first["provenance"]["scenario_version"] == first["schema_version"]


def test_course_api_exposes_manifest_fixture_and_runner(monkeypatch):
    monkeypatch.setenv("QUANTFORGE_GIT_SHA", "server-owned-sha")
    client = TestClient(app)

    manifest = client.get("/api/course/manifest")
    fixture = client.get("/api/course/fixtures/course-btc-l2-v1")
    run = client.post("/api/course/run", json={"seed": 7})

    assert manifest.status_code == 200
    assert fixture.status_code == 200
    assert run.status_code == 200
    assert run.json()["provenance"]["quantforge_git_sha"] == "server-owned-sha"
    assert run.json()["fixture"]["dataset_id"] == fixture.json()["manifest"]["dataset_id"]
    assert len(fixture.json()["events"]) == fixture.json()["manifest"]["event_count"]
    assert run.json()["export_status"] == "source_draft"


def test_course_api_rejects_client_supplied_git_provenance():
    response = TestClient(app).post(
        "/api/course/run",
        json={"seed": 7, "git_sha": "spoofed-client-sha"},
    )

    assert response.status_code == 422


def test_course_runner_marks_unknown_direction_rules_as_data_quality_warnings():
    from app.course.delta import compare_direction

    result = compare_direction("metric", "invented_direction", 1.0, 2.0)

    assert result.classification == DeltaClassification.DATA_QUALITY_WARNING


def test_default_manifest_path_supports_container_layout(monkeypatch, tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("QUANTFORGE_COURSE_MANIFEST", str(manifest))

    from app.course.schema import default_manifest_path

    assert default_manifest_path() == manifest
