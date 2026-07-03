"""Tests for multi-user support + AI-agent foundation:

- users table + pbkdf2 helpers (db.py)
- login: users table first, env-admin fallback, role embedded in JWT
- /api/admin/users CRUD (require_role("admin"))
- /api/admin/service-tokens (svc:<name> tokens for agents)
- requester = token.username on started jobs, surfaced in jobs/running
- /api/v1/runs/{run_id}/failures DuckDB fallback for manifest-less runs

These exercise the routes directly against an in-memory DuckDB (patching
server.get_connection), mirroring the pattern used in tests/test_run_lifecycle.py
and tests/test_shard.py, so no real DB file or Maven process is touched.
"""
from contextlib import ExitStack
from unittest.mock import patch

import duckdb
import jwt
import pytest
from fastapi.testclient import TestClient

from db import init_schema, NonClosingConnectionWrapper
from server import app, create_token

import server as srv


client = TestClient(app)


@pytest.fixture
def in_mem_db():
    conn = duckdb.connect(":memory:")
    init_schema(conn)
    yield NonClosingConnectionWrapper(conn)
    conn.close()


def _patched_db(in_mem_db):
    """Patch server.get_connection so every route module (system/admin/tests/runs,
    all of which call server.get_connection) sees the same in-memory connection."""
    stack = ExitStack()
    stack.enter_context(patch.object(srv, "get_connection", lambda read_only=False: in_mem_db))
    return stack


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _admin_token() -> str:
    return create_token(srv.ADMIN_USERNAME, "admin")


# ── Login ─────────────────────────────────────────────────────────────────────

def test_login_env_admin_success_sets_httponly_cookie(in_mem_db):
    with _patched_db(in_mem_db):
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": srv.ADMIN_USERNAME, "password": srv.ADMIN_PASSWORD},
        )
    assert resp.status_code == 200
    assert "token" in resp.json()
    set_cookie = resp.headers.get("set-cookie", "")
    assert "access_token=" in set_cookie
    assert "httponly" in set_cookie.lower()

    payload = jwt.decode(resp.json()["token"], srv.JWT_SECRET, algorithms=[srv.JWT_ALGORITHM])
    assert payload["sub"] == srv.ADMIN_USERNAME
    assert payload["role"] == "admin"


def test_login_wrong_password_401(in_mem_db):
    with _patched_db(in_mem_db):
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": srv.ADMIN_USERNAME, "password": "not-the-password"},
        )
    assert resp.status_code == 401


def test_db_user_login_returns_working_token_with_db_role(in_mem_db):
    srv.create_user(in_mem_db, "carol", "s3cret-pw", role="admin")
    in_mem_db.commit()

    with _patched_db(in_mem_db):
        resp = client.post("/api/v1/auth/login", json={"username": "carol", "password": "s3cret-pw"})
        assert resp.status_code == 200
        token = resp.json()["token"]

        payload = jwt.decode(token, srv.JWT_SECRET, algorithms=[srv.JWT_ALGORITHM])
        assert payload["sub"] == "carol"
        assert payload["role"] == "admin"

        # Token actually works, including for an admin-only route (proves the
        # DB-sourced role — not just the env fallback — reaches the JWT).
        admin_resp = client.get("/api/admin/users", headers=_auth(token))
    assert admin_resp.status_code == 200


# ── User management CRUD ─────────────────────────────────────────────────────

def test_users_crud_happy_path(in_mem_db):
    admin = _admin_token()
    with _patched_db(in_mem_db):
        create_resp = client.post(
            "/api/admin/users",
            json={"username": "dave", "password": "pw12345", "role": "runner"},
            headers=_auth(admin),
        )
        assert create_resp.status_code == 201
        assert create_resp.json() == {"username": "dave", "role": "runner"}

        list_resp = client.get("/api/admin/users", headers=_auth(admin))
        assert list_resp.status_code == 200
        usernames = {u["username"] for u in list_resp.json()["users"]}
        assert "dave" in usernames
        # never leak hashes
        assert all("password_hash" not in u and "salt" not in u for u in list_resp.json()["users"])

        delete_resp = client.delete("/api/admin/users/dave", headers=_auth(admin))
        assert delete_resp.status_code == 200

        list_resp2 = client.get("/api/admin/users", headers=_auth(admin))
        assert "dave" not in {u["username"] for u in list_resp2.json()["users"]}


def test_users_create_forbidden_for_non_admin(in_mem_db):
    runner_token = create_token("bob", "runner")
    with _patched_db(in_mem_db):
        resp = client.post(
            "/api/admin/users",
            json={"username": "eve", "password": "pw12345", "role": "runner"},
            headers=_auth(runner_token),
        )
    assert resp.status_code == 403


def test_users_create_duplicate_returns_409(in_mem_db):
    admin = _admin_token()
    with _patched_db(in_mem_db):
        r1 = client.post(
            "/api/admin/users",
            json={"username": "frank", "password": "pw12345", "role": "runner"},
            headers=_auth(admin),
        )
        assert r1.status_code == 201
        r2 = client.post(
            "/api/admin/users",
            json={"username": "frank", "password": "another-pw", "role": "runner"},
            headers=_auth(admin),
        )
    assert r2.status_code == 409


def test_users_delete_self_returns_400(in_mem_db):
    admin = _admin_token()
    with _patched_db(in_mem_db):
        resp = client.delete(f"/api/admin/users/{srv.ADMIN_USERNAME}", headers=_auth(admin))
    assert resp.status_code == 400


def test_users_delete_missing_returns_404(in_mem_db):
    admin = _admin_token()
    with _patched_db(in_mem_db):
        resp = client.delete("/api/admin/users/does-not-exist", headers=_auth(admin))
    assert resp.status_code == 404


def test_users_create_invalid_role_returns_422(in_mem_db):
    admin = _admin_token()
    with _patched_db(in_mem_db):
        resp = client.post(
            "/api/admin/users",
            json={"username": "gina", "password": "pw12345", "role": "superuser"},
            headers=_auth(admin),
        )
    assert resp.status_code == 422


# ── Service tokens ────────────────────────────────────────────────────────────

def test_service_token_create_and_use_records_requester(in_mem_db):
    admin = _admin_token()
    spawned = []
    with _patched_db(in_mem_db), \
         patch.object(srv, "_spawn_run", lambda rid, opts, out: spawned.append(rid)), \
         patch.object(srv, "TEST_MAX_CONCURRENCY", 1):
        create_resp = client.post(
            "/api/admin/service-tokens",
            json={"name": "ci-agent", "days": 30},
            headers=_auth(admin),
        )
        assert create_resp.status_code == 200
        body = create_resp.json()
        assert body["sub"] == "svc:ci-agent"
        assert body["role"] == "agent"
        assert body["name"] == "ci-agent"
        assert "expires_at" in body

        svc_token = body["token"]
        payload = jwt.decode(svc_token, srv.JWT_SECRET, algorithms=[srv.JWT_ALGORITHM])
        assert payload["sub"] == "svc:ci-agent"
        assert payload["role"] == "agent"

        start_resp = client.post(
            "/api/tests/start",
            json={"tags": "@smoke", "environment": "staging"},
            headers=_auth(svc_token),
        )
        assert start_resp.status_code == 200
        job_id = start_resp.json()["job_id"]

        jobs_resp = client.get("/api/tests/jobs", headers=_auth(admin))
    job = next(j for j in jobs_resp.json()["jobs"] if j["job_id"] == job_id)
    assert job["requester"] == "svc:ci-agent"


def test_service_token_forbidden_for_non_admin(in_mem_db):
    runner_token = create_token("bob", "runner")
    with _patched_db(in_mem_db):
        resp = client.post(
            "/api/admin/service-tokens",
            json={"name": "sneaky-agent"},
            headers=_auth(runner_token),
        )
    assert resp.status_code == 403


# ── requester on started jobs ────────────────────────────────────────────────

def test_start_job_as_user_sets_requester_visible_in_jobs(in_mem_db):
    alice_token = create_token("alice")  # default role "runner"
    spawned = []
    with _patched_db(in_mem_db), \
         patch.object(srv, "_spawn_run", lambda rid, opts, out: spawned.append(rid)), \
         patch.object(srv, "TEST_MAX_CONCURRENCY", 1):
        start_resp = client.post(
            "/api/tests/start",
            json={"tags": "@smoke", "environment": "staging"},
            headers=_auth(alice_token),
        )
        assert start_resp.status_code == 200
        job_id = start_resp.json()["job_id"]

        running_resp = client.get("/api/tests/running", headers=_auth(alice_token))
        jobs_resp = client.get("/api/tests/jobs", headers=_auth(alice_token))

    running_job = next(j for j in running_resp.json()["jobs"] if j["job_id"] == job_id)
    assert running_job["requester"] == "alice"

    job = next(j for j in jobs_resp.json()["jobs"] if j["job_id"] == job_id)
    assert job["requester"] == "alice"


# ── Failures DuckDB fallback ──────────────────────────────────────────────────

def _seed_failure_run(conn, run_id: str, scenario_uid: str = "uid-1"):
    conn.execute("INSERT INTO runs (id) VALUES (?)", [run_id])
    conn.execute(
        "INSERT INTO scenario_definitions (scenario_uid, identity_source, identity_key) VALUES (?, 'allure', ?)",
        [scenario_uid, f"{run_id}:{scenario_uid}"],
    )
    # Two attempts of the same scenario: first FAILED, later BROKEN — only the
    # highest retry_attempt should survive the last-attempt collapse.
    conn.execute(
        """
        INSERT INTO scenario_results
        (run_id, scenario_uid, name_at_run, status, duration_seconds, error_message,
         feature_file_at_run, doors_number_at_run, retry_attempt)
        VALUES (?, ?, 'Login fails', 'FAILED', 1.5, 'first attempt error', 'login.feature', NULL, 1)
        """,
        [run_id, scenario_uid],
    )
    conn.execute(
        """
        INSERT INTO scenario_results
        (run_id, scenario_uid, name_at_run, status, duration_seconds, error_message,
         feature_file_at_run, doors_number_at_run, retry_attempt)
        VALUES (?, ?, 'Login fails', 'BROKEN', 2.5, 'second attempt error', 'login.feature', NULL, 2)
        """,
        [run_id, scenario_uid],
    )
    conn.commit()


def test_failures_fallback_collapses_to_last_attempt(in_mem_db):
    _seed_failure_run(in_mem_db, "run-fallback-fail")

    with _patched_db(in_mem_db):
        resp = client.get("/api/v1/runs/run-fallback-fail/failures")

    assert resp.status_code == 200
    scenarios = resp.json()
    assert len(scenarios) == 1
    s = scenarios[0]
    assert s["status"] == "broken"
    assert s["steps"] == [{"name": "error", "status": "failed", "errorMessage": "second attempt error"}]


def test_failures_fallback_known_clean_run_returns_empty(in_mem_db):
    in_mem_db.execute("INSERT INTO runs (id) VALUES ('run-fallback-clean')")
    in_mem_db.commit()

    with _patched_db(in_mem_db):
        resp = client.get("/api/v1/runs/run-fallback-clean/failures")

    assert resp.status_code == 200
    assert resp.json() == []


def test_failures_fallback_unknown_run_returns_404(in_mem_db):
    with _patched_db(in_mem_db):
        resp = client.get("/api/v1/runs/run-does-not-exist-anywhere/failures")

    assert resp.status_code == 404
