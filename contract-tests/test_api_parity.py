import pytest
import requests
import json

SERVERS = [
    ("FastAPI", "http://localhost:8000"),
    ("Javalin", "http://localhost:8080"),
]


def get_token(server_url):
    r = requests.post(f"{server_url}/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    return r.json()["token"]


@pytest.mark.parametrize("name,url", SERVERS)
def test_get_runs(name, url):
    token = get_token(url)
    r = requests.get(f"{url}/api/v1/runs", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) > 0


@pytest.mark.parametrize("name,url", SERVERS)
def test_unauthorized(name, url):
    r = requests.get(f"{url}/api/v1/runs")
    assert r.status_code == 401


@pytest.mark.parametrize("name,url", SERVERS)
def test_response_keys_identical(name, url):
    token = get_token(url)
    r = requests.get(f"{url}/api/v1/runs", headers={"Authorization": f"Bearer {token}"})
    data = r.json()
    if len(data) > 0:
        expected_keys = {"runId", "timestamp", "totalScenarios", "passed", "failed", "skipped", "duration", "scenarios"}
        assert expected_keys.issubset(set(data[0].keys()))