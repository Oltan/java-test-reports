import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from models import RunManifest, ScenarioResult, StepResult, Attachment, AttemptResult


def test_load_sample_manifest():
    sample_path = Path(__file__).parent.parent.parent / "manifests" / "sample-run-001.json"
    assert sample_path.exists(), f"Sample manifest not found at {sample_path}"

    with open(sample_path) as f:
        data = json.load(f)

    manifest = RunManifest.model_validate(data)

    assert manifest.runId == "run-2026-04-26-001"
    assert manifest.totalScenarios == 3
    assert manifest.passed == 2
    assert manifest.failed == 1
    assert manifest.skipped == 0
    assert manifest.duration == "PT58.125S"
    assert len(manifest.scenarios) == 3


def test_round_trip_serialization():
    sample_path = Path(__file__).parent.parent.parent / "manifests" / "sample-run-001.json"

    with open(sample_path) as f:
        data = json.load(f)

    manifest = RunManifest.model_validate(data)

    json_str = manifest.model_dump_json(by_alias=True, exclude_none=True)
    assert '"runId"' in json_str
    assert '"totalScenarios"' in json_str

    round_trip = RunManifest.model_validate_json(json_str)
    assert round_trip.runId == manifest.runId
    assert round_trip.totalScenarios == manifest.totalScenarios


def test_passed_scenario_validation():
    sample_path = Path(__file__).parent.parent.parent / "manifests" / "sample-run-001.json"

    with open(sample_path) as f:
        data = json.load(f)

    manifest = RunManifest.model_validate(data)

    passed = next(s for s in manifest.scenarios if s.id == "scenario-001")
    assert passed.status == "passed"
    assert passed.doorsAbsNumber == "ABS-12345"
    assert len(passed.steps) == 3
    assert len(passed.attachments) == 1
    assert passed.attachments[0].type == "image/png"


def test_failed_scenario_validation():
    sample_path = Path(__file__).parent.parent.parent / "manifests" / "sample-run-001.json"

    with open(sample_path) as f:
        data = json.load(f)

    manifest = RunManifest.model_validate(data)

    failed = next(s for s in manifest.scenarios if s.id == "scenario-002")
    assert failed.status == "failed"
    assert failed.doorsAbsNumber == "ABS-12346"
    assert len(failed.steps) == 3

    error_step = failed.steps[2]
    assert error_step.errorMessage == "Payment processing failed: card declined"

    assert len(failed.attachments) == 2
    attachment_types = {a.type for a in failed.attachments}
    assert "image/png" in attachment_types
    assert "text/plain" in attachment_types


def test_step_result_model():
    step = StepResult(name="Test Step", status="passed", errorMessage=None)
    assert step.name == "Test Step"
    assert step.status == "passed"
    assert step.errorMessage is None

    step_with_error = StepResult(name="Failing Step", status="failed", errorMessage="Something went wrong")
    assert step_with_error.errorMessage == "Something went wrong"


def test_attachment_model():
    attachment = Attachment(name="screenshot.png", type="image/png", path="screenshots/screenshot.png")
    assert attachment.name == "screenshot.png"
    assert attachment.type == "image/png"
    assert attachment.path == "screenshots/screenshot.png"


def test_tags_list():
    sample_path = Path(__file__).parent.parent.parent / "manifests" / "sample-run-001.json"

    with open(sample_path) as f:
        data = json.load(f)

    manifest = RunManifest.model_validate(data)

    passed = next(s for s in manifest.scenarios if s.id == "scenario-001")
    assert "login" in passed.tags
    assert "smoke" in passed.tags
    assert "critical" in passed.tags
    assert len(passed.tags) == 3


def test_null_doors_abs_number():
    scenario = ScenarioResult(
        id="test-id",
        name="Test",
        status="skipped",
        duration="PT1S",
        doorsAbsNumber=None,
        tags=[],
        steps=[],
        attachments=[],
        attempts=[],
        dependencies=[]
    )
    assert scenario.doorsAbsNumber is None
    assert scenario.attempts == []
    assert scenario.dependencies == []


def test_attempt_result_model():
    attempt = AttemptResult(status="failed", timestamp="2026-01-01T00:00:00Z", errorMessage="Timeout")
    assert attempt.status == "failed"
    assert attempt.timestamp == "2026-01-01T00:00:00Z"
    assert attempt.errorMessage == "Timeout"

    attempt_pass = AttemptResult(status="passed", timestamp="2026-01-01T00:01:00Z")
    assert attempt_pass.errorMessage is None


def test_scenario_with_attempts_and_deps():
    scenario = ScenarioResult(
        id="retry-scenario",
        name="Retry Scenario",
        status="passed",
        duration="PT30S",
        attempts=[
            AttemptResult(status="failed", timestamp="2026-01-01T00:00:00Z", errorMessage="Error 1"),
            AttemptResult(status="failed", timestamp="2026-01-01T00:01:00Z", errorMessage="Error 2"),
            AttemptResult(status="passed", timestamp="2026-01-01T00:02:00Z"),
        ],
        dependencies=["scenario-001", "scenario-002"]
    )
    assert len(scenario.attempts) == 3
    assert scenario.attempts[0].status == "failed"
    assert scenario.attempts[2].status == "passed"
    assert scenario.dependencies == ["scenario-001", "scenario-002"]