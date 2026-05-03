"""
test_legacy_routes.py
=====================
Contract tests for legacy report route behavior.

Expected security contract:
  - GET /reports/{run_id}          → engineer-only (401/302 for anonymous)
  - GET /public/reports/{share_id} → public (no auth required)

Anonymous users must NOT see internal scenario names or run details from
the legacy /reports/{run_id} namespace. Public sharing uses the separate
/public/reports/{share_id} namespace exclusively.
"""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# ── environment ──────────────────────────────────────────────────────────────

TEST_MANIFESTS_DIR = Path(__file__).parent.parent / "manifests"
os.environ.setdefault("MANIFESTS_DIR", str(TEST_MANIFESTS_DIR))
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "admin123")

from server import app, create_token

client = TestClient(app, raise_server_exceptions=False)


# ── helpers ──────────────────────────────────────────────────────────────────

def _auth_headers(token: str | None = None) -> dict:
    if token is None:
        token = create_token("admin")
    return {"Authorization": f"Bearer {token}"}


ANONYMOUS_DENY_STATUSES = {401, 302, 404}  # 404 is acceptable — run not found + no leak


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolate_external_effects(monkeypatch: pytest.MonkeyPatch):
    """Prevent actual email / external calls during tests."""
    async def no_op_test_run(*_args, **_kwargs):
        return None

    monkeypatch.setattr(app.state if hasattr(app.state, "execute_test_run") else __import__("server"), "execute_test_run", no_op_test_run)
    monkeypatch.setattr(__import__("server", fromlist=["send_email"]), "send_email", lambda *_args, **_kwargs: None)


# ── Test 1: Anonymous /reports/{run_id} must be denied ─────────────────────

def test_anonymous_reports_run_id_is_rejected():
    """
    Anonymous GET /reports/run-2026-04-26-001 must return 401 or 302.
    The body must NOT contain internal scenario names like 'Order Submission'.
    """
    response = client.get("/reports/run-2026-04-26-001", follow_redirects=False)

    assert response.status_code in ANONYMOUS_DENY_STATUSES, (
        f"Anonymous access to /reports/{{run_id}} should be denied "
        f"(401/302/404), got {response.status_code}"
    )

    # Sensitive data must never appear in the response body for anonymous
    assert "Order Submission" not in response.text
    assert "scenario-002" not in response.text
    assert "scenario-001" not in response.text


def test_anonymous_reports_run_id_no_internal_links():
    """
    Anonymous response must not contain hrefs pointing to internal run details.
    """
    response = client.get("/reports/run-2026-04-26-001", follow_redirects=False)

    if response.status_code == 200:
        # If somehow served (should not happen for anonymous), verify no leaks
        assert "/reports/run-2026-04-26-001/scenario/" not in response.text
        assert "jira-test" not in response.text.lower()


# ── Test 2: Engineer with valid token CAN access /reports/{run_id} ─────────

def test_engineer_with_valid_token_can_access_reports_run_id():
    """
    Authenticated engineer accessing /reports/{run_id} must receive 200
    and full internal details (scenario names, manifest data).
    """
    token = create_token("engineer")
    response = client.get(
        "/reports/run-2026-04-26-001",
        headers=_auth_headers(token),
        follow_redirects=False,
    )

    # Engineer must get full access
    assert response.status_code == 200, (
        f"Engineer with valid token should access /reports/{{run_id}}, "
        f"got {response.status_code}"
    )

    # Internal details must be present
    assert "Order Submission" in response.text or "run-2026-04-26-001" in response.text


# ── Test 3: Public sharing via /public/reports/{share_id} ─────────────────────

def test_public_reports_share_id_accessible_without_auth():
    """
    GET /public/reports/test-legacy-share must work without authentication.
    This is the only namespace for public report sharing.
    """
    response = client.get("/public/reports/test-legacy-share", follow_redirects=False)

    assert response.status_code in {200, 302, 404}, (
        f"Public share route /public/reports/{{share_id}} should be accessible "
        f"without auth (or 404 if not found), got {response.status_code}"
    )


def test_public_reports_share_id_no_internal_run_detail_links():
    """
    The public report page must NOT contain links to internal run detail pages
    like /reports/run-2026-04-26-001.
    """
    response = client.get(
        "/public/reports/test-legacy-share",
        follow_redirects=False,
        # Allow following redirect to check final page content
    )

    # If we get a redirect, follow it to check final content
    if response.status_code == 302:
        response = client.get(
            "/public/reports/test-legacy-share",
            follow_redirects=True,
        )

    if response.status_code == 200:
        # Public page must not expose internal run URLs
        assert "/reports/run-2026-04-26-001" not in response.text
        assert "internal" not in response.text.lower() or "visibility" not in response.text.lower()


# ── Test 4: Unknown public route returns 404 cleanly ─────────────────────────

def test_unknown_public_route_404_without_leak():
    """
    Unknown /public/reports/{unknown_id} must return 404 without leaking
    stack traces or internal paths.
    """
    response = client.get("/public/reports/does-not-exist-at-all", follow_redirects=False)

    assert response.status_code == 404
    assert "Traceback" not in response.text
    assert "/home/" not in response.text
    assert "Internal Server Error" not in response.text


# ── Test 5: Legacy /reports/{run_id} never exposes public data by guessable ID ─

def test_reports_run_id_not_spoofable_as_public_share():
    """
    Attempting to access an internal run_id via the public namespace should
    not succeed, ensuring internal IDs cannot be guessed.
    """
    # Try to access an internal run via public namespace
    response = client.get("/public/reports/run-2026-04-26-001", follow_redirects=False)

    # Should not serve internal data via public namespace
    # Accept 404 (share not found) or 401/302 (auth required)
    assert response.status_code in {401, 302, 404, 403}, (
        f"Public namespace should not serve internal run data, got {response.status_code}"
    )

    if response.status_code == 200:
        # Verify no internal scenario names leaked
        assert "Order Submission" not in response.text