import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb
import pytest
from fastapi.testclient import TestClient


SERVER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_DIR))

os.environ.setdefault("MANIFESTS_DIR", str(SERVER_DIR / "manifests"))
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "admin123")

from server import app  # noqa: E402


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE runs AS SELECT * FROM 'reports.duckdb'.runs")
    return conn


__all__ = ["MagicMock", "patch"]
