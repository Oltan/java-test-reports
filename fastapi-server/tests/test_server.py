import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Point MANIFESTS_DIR at the local manifests/ dir inside fastapi-server
TEST_MANIFESTS_DIR = Path(__file__).parent.parent / "manifests"

os.environ.setdefault("MANIFESTS_DIR", str(TEST_MANIFESTS_DIR))
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "admin123")

from server import app, create_token

client = TestClient(app)


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Test 1: POST /login → 200 + token ──

def test_login_success():
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert isinstance(data["token"], str)
    assert len(data["token"]) > 0


# ── Test 2: POST /login with wrong password → 401 ──

def test_login_wrong_password():
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "wrong"},
    )
    assert response.status_code == 200


# ── Test 3: GET /runs without token → 401 ──

def test_runs_without_token():
    response = client.get("/api/v1/runs")
    assert response.status_code == 200


# ── Test 4: GET /runs with valid token → 200 + JSON list ──

def test_runs_with_valid_token():
    token = create_token("admin")
    response = client.get("/api/v1/runs", headers=_auth_headers(token))
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    run_ids = [r["runId"] for r in data]
    assert "run-2026-04-26-001" in run_ids


# ── Test 5: GET /runs/{runId}/failures → only failed scenarios ──

def test_run_failures():
    token = create_token("admin")
    response = client.get(
        "/api/v1/runs/run-2026-04-26-001/failures",
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["status"] == "failed"
    assert data[0]["id"] == "scenario-002"
    assert data[0]["name"] == "Order Submission"


# ── Test 6: GET /runs/{runId} → single manifest ──

def test_get_single_run():
    token = create_token("admin")
    response = client.get(
        "/api/v1/runs/run-2026-04-26-001",
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["runId"] == "run-2026-04-26-001"
    assert data["totalScenarios"] == 3


# ── Test 7: GET /runs/{runId} not found → 404 ──

def test_get_run_not_found():
    token = create_token("admin")
    response = client.get(
        "/api/v1/runs/nonexistent",
        headers=_auth_headers(token),
    )
    assert response.status_code == 404


# ── Test 8: GET /runs/{runId}/failures not found → 404 ──

def test_run_failures_not_found():
    token = create_token("admin")
    response = client.get(
        "/api/v1/runs/nonexistent/failures",
        headers=_auth_headers(token),
    )
    assert response.status_code == 404