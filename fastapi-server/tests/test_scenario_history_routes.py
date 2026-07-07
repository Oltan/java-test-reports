"""Regression tests: scenario-history/matrix endpoints against a real file-backed DuckDB.

These endpoints used to open the connection with read_only=True and then call
init_schema (CREATE TABLE ...), which DuckDB rejects on read-only connections
("Cannot execute statement of type CREATE ... read-only mode") → HTTP 500.
The unit suite never caught it because fixtures monkeypatch get_connection with
an in-memory connection. Here we go through the real db.get_connection against
a temporary database file.
"""
import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "admin123")

import db
from server import app, create_token

client = TestClient(app)


@pytest.fixture
def file_db(tmp_path, monkeypatch):
    """Point db.get_connection at a fresh on-disk DuckDB file (no monkeypatched connection)."""
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "reports-test.duckdb"))
    yield


def _headers():
    return {"Authorization": f"Bearer {create_token('admin')}"}


def test_scenario_history_real_db(file_db):
    resp = client.get("/api/scenario-history", headers=_headers())
    assert resp.status_code == 200
    assert resp.json() == []


def test_scenario_history_item_real_db(file_db):
    resp = client.get("/api/scenario-history/ABS-99999", headers=_headers())
    assert resp.status_code == 404  # empty DB → not found, not 500


def test_scenario_matrix_real_db(file_db):
    resp = client.get("/api/scenario-matrix", headers=_headers())
    assert resp.status_code == 200
