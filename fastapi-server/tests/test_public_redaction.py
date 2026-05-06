import json
from datetime import datetime, timezone

import pytest

import models


FORBIDDEN_FIELDS = {
    "jira_key",
    "doors_abs_number",
    "doors_id",
    "is_flaky",
    "attempts",
    "dependencies",
    "tags",
    "feature",
    "attachments",
    "logs",
    "stack_trace",
    "raw_attachment_path",
}

ALLOWED_TOP_LEVEL_FIELDS = {
    "run_summary",
    "scenario_list",
    "generated_timestamp",
    "total_passed",
    "total_failed",
    "total_skipped",
}

ALLOWED_SCENARIO_FIELDS = {"name", "status"}

SENSITIVE_VALUES = [
    "BUG-7421",
    "JIRA-9081",
    "ABS-SEC-101",
    "DOORS-SEC-101",
    "@payment",
    "@pci",
    "features/payments/card_decline.feature",
    "Retry attempt 1 failed with gateway timeout",
    "Traceback (most recent call last)",
    "/var/ci/allure-results/raw/attachment-stacktrace.txt",
]


@pytest.fixture
def internal_report_snapshot():
    return {
        "runId": "raw-run-id-must-not-be-shared",
        "timestamp": "2026-05-03T08:15:30Z",
        "totalScenarios": 3,
        "passed": 1,
        "failed": 1,
        "skipped": 1,
        "duration": "PT42.000S",
        "generated_timestamp": datetime(2026, 5, 3, 8, 16, tzinfo=timezone.utc),
        "scenarios": [
            {
                "id": "scenario-internal-001",
                "name": "Card decline shows safe public result",
                "status": "failed",
                "duration": "PT12.345S",
                "jira_key": "BUG-7421",
                "doors_abs_number": "ABS-SEC-101",
                "doors_id": "DOORS-SEC-101",
                "is_flaky": True,
                "attempts": [
                    {
                        "status": "failed",
                        "timestamp": "2026-05-03T08:15:31Z",
                        "errorMessage": "Retry attempt 1 failed with gateway timeout",
                    },
                    {
                        "status": "passed",
                        "timestamp": "2026-05-03T08:15:42Z",
                    },
                ],
                "dependencies": ["scenario-internal-000"],
                "tags": ["@payment", "@pci"],
                "feature": "features/payments/card_decline.feature",
                "attachments": [
                    {
                        "name": "stacktrace.txt",
                        "type": "text/plain",
                        "path": "/var/ci/allure-results/raw/attachment-stacktrace.txt",
                    }
                ],
                "logs": ["Retry attempt 1 failed with gateway timeout"],
                "stack_trace": "Traceback (most recent call last): RuntimeError: gateway timeout",
                "raw_attachment_path": "/var/ci/allure-results/raw/attachment-stacktrace.txt",
            },
            {
                "id": "scenario-internal-002",
                "name": "Happy path stays public",
                "status": "passed",
                "duration": "PT10.000S",
                "jira_key": None,
                "doors_abs_number": None,
                "doors_id": None,
                "is_flaky": False,
                "attempts": [],
                "dependencies": [],
                "tags": ["@smoke"],
                "feature": "features/payments/happy_path.feature",
                "attachments": [],
                "logs": [],
                "stack_trace": None,
                "raw_attachment_path": None,
            },
            {
                "id": "scenario-internal-003",
                "name": "Skipped dependency stays public",
                "status": "skipped",
                "duration": "PT0.000S",
                "jira_key": "JIRA-9081",
                "doors_abs_number": "ABS-SEC-102",
                "doors_id": "DOORS-SEC-102",
                "is_flaky": False,
                "attempts": [],
                "dependencies": ["scenario-internal-001"],
                "tags": ["@blocked"],
                "feature": "features/payments/skipped_dependency.feature",
                "attachments": [],
                "logs": ["Blocked by internal dependency scenario-internal-001"],
                "stack_trace": None,
                "raw_attachment_path": None,
            },
        ],
    }


@pytest.fixture
def expected_public_payload():
    return {
        "run_summary": {
            "total_scenarios": 3,
            "passed": 1,
            "failed": 1,
            "skipped": 1,
        },
        "scenario_list": [
            {"name": "Card decline shows safe public result", "status": "failed"},
            {"name": "Happy path stays public", "status": "passed"},
            {"name": "Skipped dependency stays public", "status": "skipped"},
        ],
        "generated_timestamp": "2026-05-03T08:16:00Z",
        "total_passed": 1,
        "total_failed": 1,
        "total_skipped": 1,
    }


def _serialize_public_payload(internal_report: dict) -> dict:
    assert hasattr(models, "PublicReportSnapshot"), (
        "models.PublicReportSnapshot must build a public allowlist payload before "
        "public reports can be exposed."
    )

    snapshot_cls = getattr(models, "PublicReportSnapshot")
    assert hasattr(snapshot_cls, "from_internal"), (
        "PublicReportSnapshot.from_internal(internal_report) must construct a new "
        "allowlisted public DTO instead of mutating internal report data at render time."
    )

    snapshot = snapshot_cls.from_internal(internal_report)
    if hasattr(snapshot, "model_dump"):
        return snapshot.model_dump(mode="json", exclude_none=True)
    return dict(snapshot)


def _walk_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def test_public_snapshot_uses_allowlist_shape(
    internal_report_snapshot,
    expected_public_payload,
):
    payload = _serialize_public_payload(internal_report_snapshot)

    assert set(payload) == ALLOWED_TOP_LEVEL_FIELDS
    assert payload == expected_public_payload
    assert all(set(scenario) == ALLOWED_SCENARIO_FIELDS for scenario in payload["scenario_list"])


@pytest.mark.parametrize("forbidden_field", sorted(FORBIDDEN_FIELDS))
def test_public_snapshot_redacts_forbidden_keys_recursively(
    internal_report_snapshot,
    forbidden_field,
):
    payload = _serialize_public_payload(internal_report_snapshot)

    assert forbidden_field not in set(_walk_keys(payload))


@pytest.mark.parametrize("sensitive_value", SENSITIVE_VALUES)
def test_public_snapshot_redacts_sensitive_values(
    internal_report_snapshot,
    sensitive_value,
):
    payload = _serialize_public_payload(internal_report_snapshot)

    serialized = json.dumps(payload, sort_keys=True)

    assert sensitive_value not in serialized
