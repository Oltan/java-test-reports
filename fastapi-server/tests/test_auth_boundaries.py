import os
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "admin123")

import server


client = TestClient(server.app)


ANONYMOUS_DENY_STATUSES = {401, 302}

ENGINEER_ONLY_ROUTES = [
    ("GET", "/admin", None),
    ("GET", "/dashboard", None),
    ("GET", "/reports/merge", None),
    ("GET", "/reports/run-2026-04-26-001", None),
    ("GET", "/reports/run-2026-04-26-001/triage", None),
    (
        "POST",
        "/api/tests/start",
        {
            "json": {
                "tags": "@smoke",
                "retry_count": 0,
                "browser": "chrome",
                "parallel": 1,
                "environment": "staging",
                "visibility": "internal",
            },
        },
    ),
    ("POST", "/api/tests/run-2026-04-26-001/cancel", None),
    ("POST", "/api/v1/runs/run-2026-04-26-001/scenarios/scenario-002/jira", None),
    ("POST", "/api/doors/run", {"json": {"script": "print('anonymous probe')"}}),
    (
        "POST",
        "/api/email/send",
        {"params": {"to": "security@example.invalid", "run_id": "run-2026-04-26-001"}},
    ),
]

PUBLIC_ALLOWLIST_ROUTES = [
    (
        "POST",
        "/api/v1/auth/login",
        {"json": {"username": "admin", "password": "admin123"}},
        200,
    ),
]

HIGH_RISK_PUBLIC_WRITES = [route for route in ENGINEER_ONLY_ROUTES if route[0] == "POST"]


def _request(method: str, path: str, kwargs: dict | None = None):
    return client.request(method, path, follow_redirects=False, **(kwargs or {}))


@pytest.fixture(autouse=True)
def isolate_external_write_effects(monkeypatch: pytest.MonkeyPatch):
    async def no_op_test_run(*_args, **_kwargs):
        return None

    monkeypatch.setattr(server, "execute_test_run", no_op_test_run)
    monkeypatch.setattr(server, "is_doors_available", lambda: False)
    monkeypatch.setattr(server, "send_email", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server.jira_client, "is_configured", lambda: False)


@pytest.mark.parametrize(("method", "path", "kwargs"), ENGINEER_ONLY_ROUTES)
def test_anonymous_engineer_routes_require_auth(method: str, path: str, kwargs: dict | None):
    response = _request(method, path, kwargs)

    assert response.status_code in ANONYMOUS_DENY_STATUSES


@pytest.mark.parametrize(("method", "path", "kwargs"), HIGH_RISK_PUBLIC_WRITES)
def test_anonymous_write_actions_require_auth(method: str, path: str, kwargs: dict | None):
    response = _request(method, path, kwargs)

    assert response.status_code in ANONYMOUS_DENY_STATUSES


@pytest.mark.parametrize(("method", "path", "kwargs", "expected_status"), PUBLIC_ALLOWLIST_ROUTES)
def test_public_allowlist_remains_anonymous(method: str, path: str, kwargs: dict, expected_status: int):
    response = _request(method, path, kwargs)

    assert response.status_code == expected_status
    assert "Traceback" not in response.text
    assert "Internal Server Error" not in response.text
    assert "/home/" not in response.text


def test_unknown_public_route_returns_404_without_internal_leakage():
    response = client.get("/public/does-not-exist", follow_redirects=False)

    assert response.status_code == 404
    assert "Traceback" not in response.text
    assert "Internal Server Error" not in response.text
    assert "/home/" not in response.text


def test_anonymous_test_status_websocket_rejected():
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/test-status/run-2026-04-26-001"):
            pass
