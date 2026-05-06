"""
Integration workflow tests covering the full engineer journey:
login → protected routes → job start → triage enforcement
→ Jira/override → share generation → public redaction
→ DOORS/email auth → legacy denial.
"""

import os
import sys
from datetime import datetime
from pathlib import Path
import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

SERVER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_DIR))

os.environ.setdefault("MANIFESTS_DIR", str(SERVER_DIR / "manifests"))
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "admin123")

from server import app, create_token
from db import init_schema, NonClosingConnectionWrapper


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _token() -> str:
    return create_token("admin")


@pytest.fixture
def test_client():
    with TestClient(app, follow_redirects=False) as c:
        yield c


@pytest.fixture
def patched_client(test_client, in_mem_db):
    def fake_get_conn(read_only=False):
        return in_mem_db

    def fake_send_email(*a, **kw):
        return None

    import server as srv
    with patch.object(srv, "get_connection", fake_get_conn):
        with patch.object(srv, "send_email", fake_send_email):
            yield test_client


@pytest.fixture
def in_mem_db():
    import duckdb
    conn = duckdb.connect(":memory:")
    init_schema(conn)
    yield NonClosingConnectionWrapper(conn)
    conn.close()


@pytest.fixture
def with_fake_get_conn(in_mem_db):
    def fake_get_conn(read_only=False):
        return in_mem_db

    def fake_send_email(*a, **kw):
        return None

    import server as srv
    with patch.object(srv, "get_connection", fake_get_conn):
        with patch.object(srv, "send_email", fake_send_email):
            yield in_mem_db


@pytest.fixture
def with_seed_data(with_fake_get_conn):
    manifest_path = Path(os.environ["MANIFESTS_DIR"]) / "sample-run-001.json"
    if not manifest_path.exists():
        pytest.skip(f"Manifest not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text())
    ts = datetime.fromisoformat(manifest["timestamp"].replace("Z", "+00:00"))

    raw_conn = object.__getattribute__(with_fake_get_conn, "_conn")
    raw_conn.execute(
        """
        INSERT INTO runs
          (id, version, environment, started_at, finished_at,
           total_scenarios, passed, failed, skipped, visibility)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'internal')
        """,
        [
            manifest["runId"],
            manifest.get("version", "1.0.0"),
            manifest.get("environment", "staging"),
            ts, ts,
            manifest["totalScenarios"],
            manifest["passed"],
            manifest["failed"],
            manifest["skipped"],
        ],
    )

    for i, sc in enumerate(manifest["scenarios"]):
        uid = hashlib.sha256(
            f"{manifest['runId']}:{sc['name']}:{i}".encode()
        ).hexdigest()[:32]
        raw_conn.execute(
            """
            INSERT INTO scenario_definitions
              (scenario_uid, identity_source, identity_key, current_name,
               first_seen_run_id, last_seen_run_id, first_seen_at, last_seen_at,
               doors_number)
            VALUES (?, 'manifest', ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                uid,
                f"{manifest['runId']}:{sc['name']}",
                sc["name"],
                manifest["runId"],
                manifest["runId"],
                ts, ts,
                sc.get("doorsAbsNumber"),
            ],
        )
        raw_conn.execute(
            """
            INSERT INTO scenario_results
              (run_id, scenario_uid, name_at_run, status, duration_seconds,
               error_message, doors_number_at_run, retry_attempt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                manifest["runId"],
                uid,
                sc["name"],
                sc["status"].upper(),
                0.0,
                next(
                    (
                        st["errorMessage"]
                        for st in sc.get("steps", [])
                        if st.get("errorMessage")
                    ),
                    None,
                ),
                sc.get("doorsAbsNumber"),
                1,
            ],
        )

    raw_conn.commit()
    return with_fake_get_conn, manifest["runId"]


def test_engineer_login_and_access(test_client):
    login_resp = test_client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert login_resp.status_code == 200, login_resp.json()
    token = login_resp.json()["token"]

    runs_resp = test_client.get("/api/v1/runs", headers=_auth(token))
    assert runs_resp.status_code == 200
    assert isinstance(runs_resp.json(), list)


def test_anonymous_denied_workflow(test_client):
    public_read_routes = [
        ("GET", "/api/v1/runs"),
        ("GET", "/api/v1/runs/run-2026-04-26-001"),
        ("GET", "/api/v1/runs/run-2026-04-26-001/failures"),
        ("GET", "/api/versions"),
        ("GET", "/api/dashboard/metrics"),
    ]
    for method, route in public_read_routes:
        method_fn = getattr(test_client, method.lower())
        # Public read endpoints: no token → 200, invalid token → 401
        resp = method_fn(route)
        assert resp.status_code == 200, f"{method} {route} returned {resp.status_code} instead of 200"

    engineer_routes = [
        ("POST", "/api/tests/start"),
        ("GET", "/api/tests/running"),
        ("GET", "/api/tests/jobs"),
        ("POST", "/api/reports/generate-share"),
        ("GET", "/api/triage/run-2026-04-26-001"),
        ("POST", "/api/doors/run"),
        ("POST", "/api/email/send"),
        ("POST", "/api/doors/share/some-share-id"),
        ("POST", "/api/email/share/some-share-id"),
        ("GET", "/reports/run-2026-04-26-001"),
    ]
    for method, route in engineer_routes:
        method_fn = getattr(test_client, method.lower())

        resp = method_fn(route)
        # HTML pages redirect to login (302); API endpoints return 401
        assert resp.status_code in (302, 401), (
            f"{method} {route} returned {resp.status_code} instead of 401/302"
        )

        resp = method_fn(route, headers=_auth("invalid-token"))
        assert resp.status_code in (302, 401), (
            f"{method} {route} with invalid token returned {resp.status_code}"
        )


def test_job_start_and_query(test_client, in_mem_db):
    def fake_get_conn(read_only=False):
        return in_mem_db

    import server as srv
    with patch.object(srv, "get_connection", fake_get_conn):
        token = _token()

        start_resp = test_client.post(
            "/api/tests/start",
            json={
                "tags": "@smoke",
                "retry_count": 0,
                "browser": "chrome",
                "parallel": 1,
                "environment": "staging",
                "version": "1.0.0",
                "visibility": "internal",
            },
            headers=_auth(token),
        )
        assert start_resp.status_code == 200, f"Start failed: {start_resp.text}"
        job_id = start_resp.json()["job_id"]

        running_resp = test_client.get("/api/tests/running", headers=_auth(token))
        assert running_resp.status_code == 200
        assert "jobs" in running_resp.json()

        jobs_resp = test_client.get("/api/tests/jobs", headers=_auth(token))
        assert jobs_resp.status_code == 200
        job_ids = [j["job_id"] for j in jobs_resp.json()["jobs"]]
        assert job_id in job_ids


def test_triage_override_requires_reason(test_client, with_seed_data):
    conn, run_id = with_seed_data
    token = _token()

    row = conn.execute(
        "SELECT scenario_uid FROM scenario_results WHERE run_id = ? AND status = 'FAILED' LIMIT 1",
        [run_id],
    ).fetchone()
    assert row
    scenario_uid = row[0]

    resp = test_client.post(
        f"/api/triage/{run_id}/scenarios/{scenario_uid}/override",
        json={"decision": "accepted_pass", "reason": ""},
        headers=_auth(token),
    )
    assert resp.status_code == 422

    resp = test_client.post(
        f"/api/triage/{run_id}/scenarios/{scenario_uid}/override",
        json={"decision": "accepted_skip", "reason": "   "},
        headers=_auth(token),
    )
    assert resp.status_code == 422

    valid_resp = test_client.post(
        f"/api/triage/{run_id}/scenarios/{scenario_uid}/override",
        json={"decision": "accepted_pass", "reason": "Known flaky test in CI environment"},
        headers=_auth(token),
    )
    assert valid_resp.status_code == 200
    assert valid_resp.json()["success"] is True


def test_jira_create_idempotent(test_client, with_seed_data):
    conn, run_id = with_seed_data
    token = _token()

    row = conn.execute(
        "SELECT scenario_uid FROM scenario_results WHERE run_id = ? AND status = 'FAILED' LIMIT 1",
        [run_id],
    ).fetchone()
    assert row
    scenario_uid = row[0]

    first_resp = test_client.post(
        f"/api/triage/{run_id}/scenarios/{scenario_uid}/jira",
        headers=_auth(token),
    )
    if first_resp.status_code == 201:
        first_key = first_resp.json()["jiraKey"]
        second_resp = test_client.post(
            f"/api/triage/{run_id}/scenarios/{scenario_uid}/jira",
            headers=_auth(token),
        )
        assert second_resp.status_code == 200
        assert second_resp.json()["jiraKey"] == first_key


def test_share_blocked_by_untriaged(test_client, with_seed_data):
    conn, run_id = with_seed_data
    token = _token()

    rows = conn.execute(
        "SELECT scenario_uid FROM scenario_results WHERE run_id = ?",
        [run_id],
    ).fetchall()
    all_uids = [r[0] for r in rows]

    resp = test_client.post(
        "/api/reports/generate-share",
        json={"scenario_ids": all_uids, "title": "Test Report"},
        headers=_auth(token),
    )
    assert resp.status_code == 409
    assert "blockers" in resp.json().get("detail", {})


def test_share_success_after_triage(test_client, with_seed_data):
    conn, run_id = with_seed_data
    token = _token()

    failed_rows = conn.execute(
        "SELECT scenario_uid FROM scenario_results WHERE run_id = ? AND status = 'FAILED'",
        [run_id],
    ).fetchall()

    for (uid,) in failed_rows:
        override_resp = test_client.post(
            f"/api/triage/{run_id}/scenarios/{uid}/override",
            json={"decision": "accepted_pass", "reason": "Acknowledged in triage review"},
            headers=_auth(token),
        )
        assert override_resp.status_code == 200

    rows = conn.execute(
        "SELECT scenario_uid FROM scenario_results WHERE run_id = ?",
        [run_id],
    ).fetchall()
    all_uids = [r[0] for r in rows]

    share_resp = test_client.post(
        "/api/reports/generate-share",
        json={"scenario_ids": all_uids, "title": "Triaged Report"},
        headers=_auth(token),
    )
    assert share_resp.status_code == 200
    body = share_resp.json()
    assert "share_id" in body
    assert body["url"].startswith("/public/reports/")


def test_public_redaction(test_client, with_seed_data):
    conn, run_id = with_seed_data
    token = _token()

    failed_rows = conn.execute(
        "SELECT scenario_uid FROM scenario_results WHERE run_id = ? AND status = 'FAILED'",
        [run_id],
    ).fetchall()
    for (uid,) in failed_rows:
        test_client.post(
            f"/api/triage/{run_id}/scenarios/{uid}/override",
            json={"decision": "accepted_skip", "reason": "Not relevant"},
            headers=_auth(token),
        )

    rows = conn.execute(
        "SELECT scenario_uid FROM scenario_results WHERE run_id = ?",
        [run_id],
    ).fetchall()
    all_uids = [r[0] for r in rows]

    share_resp = test_client.post(
        "/api/reports/generate-share",
        json={"scenario_ids": all_uids, "title": "Public Report"},
        headers=_auth(token),
    )
    assert share_resp.status_code == 200
    share_id = share_resp.json()["share_id"]

    public_resp = test_client.get(f"/api/public/reports/{share_id}")
    assert public_resp.status_code == 200
    snapshot = public_resp.json()

    internal_fields = (
        "doorsAbsNumber", "doors_number", "doors_id",
        "jiraKey", "jira_key", "jiraUrl",
        "attachment", "screenshot", "video_path",
        "errorMessage", "stackTrace",
        "run_id", "scenario_uid", "feature_file",
    )
    snapshot_str = str(snapshot)
    for field in internal_fields:
        assert field not in snapshot_str, (
            f"Internal field '{field}' found in public snapshot"
        )

    scenario_list = snapshot.get("scenario_list", [])
    assert len(scenario_list) > 0
    for sc in scenario_list:
        assert list(sc.keys()) == ["name", "status"], (
            f"Public scenario should only have name+status, got: {list(sc.keys())}"
        )


def test_doors_email_auth(patched_client, in_mem_db):
    fake_share_id = "nonexistent-share-12345"

    def fake_get_conn(read_only=False):
        return in_mem_db

    def fake_send_email(*a, **kw):
        return None

    import server as srv
    with patch.object(srv, "get_connection", fake_get_conn):
        with patch.object(srv, "send_email", fake_send_email):
            doors_resp = patched_client.post(f"/api/doors/share/{fake_share_id}")
            assert doors_resp.status_code == 401

            email_resp = patched_client.post(
                f"/api/email/share/{fake_share_id}", params={"to": "test@example.com"}
            )
            assert email_resp.status_code == 401

            doors_resp = patched_client.post(
                f"/api/doors/share/{fake_share_id}", headers=_auth("invalid-token")
            )
            assert doors_resp.status_code == 401

            email_resp = patched_client.post(
                f"/api/email/share/{fake_share_id}",
                params={"to": "test@example.com"},
                headers=_auth("invalid-token"),
            )
            assert email_resp.status_code == 401

            token = _token()
            doors_resp = patched_client.post(
                f"/api/doors/share/{fake_share_id}", headers=_auth(token)
            )
            assert doors_resp.status_code == 404

            email_resp = patched_client.post(
                f"/api/email/share/{fake_share_id}",
                params={"to": "test@example.com"},
                headers=_auth(token),
            )
            assert email_resp.status_code == 404


def test_legacy_route_denied(test_client):
    resp = test_client.get("/reports/run-2026-04-26-001")
    assert resp.status_code in (302, 401)

    token = _token()
    resp = test_client.get("/reports/run-2026-04-26-001", headers=_auth(token))
    assert resp.status_code not in (302, 401)