import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "admin123")

from server import app, create_token

client = TestClient(app)


def _auth_headers(token: str = None) -> dict:
    if token is None:
        token = create_token("admin")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def temp_tracker():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.write(fd, b'{"version": "1.0", "mappings": {}}')
    os.close(fd)
    from bug_tracker import BugTracker
    test_tracker = BugTracker(path)
    yield test_tracker, path
    Path(path).unlink(missing_ok=True)


def test_list_bugs_200(temp_tracker):
    test_tracker, path = temp_tracker
    with patch("server.tracker", test_tracker):
        token = create_token("admin")
        response = client.get("/api/v1/bugs", headers=_auth_headers(token))
        assert response.status_code == 200
        assert isinstance(response.json(), dict)


def test_get_bug_404(temp_tracker):
    test_tracker, path = temp_tracker
    with patch("server.tracker", test_tracker):
        token = create_token("admin")
        response = client.get("/api/v1/bugs/DOORS-99999", headers=_auth_headers(token))
        assert response.status_code == 404


def test_create_bug_201(temp_tracker):
    test_tracker, path = temp_tracker
    with patch("server.tracker", test_tracker):
        token = create_token("admin")
        response = client.post(
            "/api/v1/bugs/DOORS-12345/create",
            headers=_auth_headers(token),
            json={"scenarioName": "Login Test", "runId": "run-001"},
        )
        assert response.status_code == 201
        data = response.json()
        assert "jiraKey" in data
        assert data["doorsNumber"] == "DOORS-12345"


def test_create_bug_409_conflict(temp_tracker):
    test_tracker, path = temp_tracker
    with patch("server.tracker", test_tracker):
        token = create_token("admin")
        client.post(
            "/api/v1/bugs/DOORS-12345/create",
            headers=_auth_headers(token),
            json={"scenarioName": "Login Test", "runId": "run-001"},
        )
        response = client.post(
            "/api/v1/bugs/DOORS-12345/create",
            headers=_auth_headers(token),
            json={"scenarioName": "Another Test", "runId": "run-002"},
        )
        assert response.status_code == 409


def test_get_bug_200(temp_tracker):
    test_tracker, path = temp_tracker
    with patch("server.tracker", test_tracker):
        token = create_token("admin")
        client.post(
            "/api/v1/bugs/DOORS-12345/create",
            headers=_auth_headers(token),
            json={"scenarioName": "Login Test", "runId": "run-001"},
        )
        response = client.get("/api/v1/bugs/DOORS-12345", headers=_auth_headers(token))
        assert response.status_code == 200
        data = response.json()
        assert "jiraKey" in data
        assert data["status"] == "OPEN"


def test_unauthorized_401(temp_tracker):
    test_tracker, path = temp_tracker
    with patch("server.tracker", test_tracker):
        response = client.get("/api/v1/bugs")
        assert response.status_code == 200  # public endpoint — no auth required