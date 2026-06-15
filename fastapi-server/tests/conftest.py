import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb
import pytest
from fastapi.testclient import TestClient


SERVER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_DIR))

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# server.py resolves MANIFESTS_DIR from the environment at import time, so the
# manifests directory must be prepared BEFORE `from server import app` runs
# anywhere in the session. Use a per-session temp dir populated from the
# checked-in fixtures so test runs are hermetic and repeatable (the real
# manifests/ directory is gitignored and absent on a fresh clone).
_MANIFESTS_TMP_DIR = Path(tempfile.mkdtemp(prefix="test-manifests-"))
atexit.register(shutil.rmtree, _MANIFESTS_TMP_DIR, ignore_errors=True)
for _fixture in sorted(FIXTURES_DIR.glob("*.json")):
    shutil.copy(_fixture, _MANIFESTS_TMP_DIR / _fixture.name)

os.environ["MANIFESTS_DIR"] = str(_MANIFESTS_TMP_DIR)
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "admin123")
# Don't run startup orphan-recovery against the real DB during tests; the
# recovery logic is exercised directly in test_run_lifecycle.py instead.
os.environ.setdefault("RUN_RECOVERY_ON_STARTUP", "0")

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
