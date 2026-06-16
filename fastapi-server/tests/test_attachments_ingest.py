"""Characterization tests for attachment ingest (P5-deep).

_save_results_to_duckdb / _parse_allure_result had no direct coverage; these
pin the new behaviour: parsing Allure attachments, copying them under
MANIFESTS_DIR, and recording servable paths on scenario_results + the manifest.
"""
import json
from datetime import datetime
from unittest.mock import patch

import duckdb
import pytest

from db import init_schema, NonClosingConnectionWrapper
from models import TestRunOptions as RunOpts


def _allure_result(**over):
    now_ms = int(datetime.now().timestamp() * 1000)
    base = {
        "name": "Login fails",
        "fullName": "login.feature:Login fails",
        "status": "failed",
        "time": {"duration": 1200},
        "statusDetails": {"message": "boom"},
        "labels": [{"name": "tag", "value": "@DOORS-1"}],
        "historyId": "hist-abc",
        "start": now_ms,
        "steps": [
            {"name": "step", "status": "failed",
             "attachments": [{"name": "shot", "source": "s1.png", "type": "image/png"}]},
        ],
        "attachments": [{"name": "rec", "source": "v1.mp4", "type": "video/mp4"}],
    }
    base.update(over)
    return base


def test_parse_allure_result_extracts_attachments(tmp_path):
    import server as srv
    f = tmp_path / "x-result.json"
    f.write_text(json.dumps(_allure_result()))
    parsed = srv._parse_allure_result(f)
    assert {"name": "shot", "type": "image/png", "source": "s1.png"} in parsed["attachments"]
    assert {"name": "rec", "type": "video/mp4", "source": "v1.mp4"} in parsed["attachments"]
    assert parsed["screenshot_source"] == "s1.png"
    assert parsed["video_source"] == "v1.mp4"


def test_copy_run_attachment(tmp_path):
    import server as srv
    allure = tmp_path / "allure"; allure.mkdir()
    (allure / "s1.png").write_bytes(b"PNGDATA")
    manifests = tmp_path / "manifests"
    with patch.object(srv, "MANIFESTS_DIR", manifests):
        rel = srv._copy_run_attachment(allure, "run-1", "s1.png")
        assert rel == "run-1/s1.png"
        assert (manifests / "run-1" / "s1.png").read_bytes() == b"PNGDATA"
        assert srv._copy_run_attachment(allure, "run-1", None) is None
        assert srv._copy_run_attachment(allure, "run-1", "missing.png") is None


def test_save_results_populates_attachment_paths(tmp_path):
    import server as srv
    allure = tmp_path / "allure"; allure.mkdir()
    (allure / "s1.png").write_bytes(b"PNG")
    (allure / "v1.mp4").write_bytes(b"MP4")
    (allure / "x-result.json").write_text(json.dumps(_allure_result()))

    manifests = tmp_path / "manifests"  # both copy-root and manifest-dir resolve here
    conn = duckdb.connect(":memory:"); init_schema(conn)
    wrapped = NonClosingConnectionWrapper(conn)
    opts = RunOpts(tags="@smoke", environment="staging")

    with patch.object(srv, "get_connection", lambda read_only=False: wrapped), \
         patch.object(srv, "MANIFESTS_DIR", manifests), \
         patch.object(srv, "PROJECT_ROOT", tmp_path):
        srv._save_results_to_duckdb("run-att", opts, started_at=datetime.now(), allure_dir=str(allure))

    row = conn.execute(
        "SELECT screenshot_path, video_path FROM scenario_results WHERE run_id = 'run-att'"
    ).fetchone()
    conn.close()
    assert row is not None, "scenario was ingested"
    assert row[0] == "run-att/s1.png"
    assert row[1] == "run-att/v1.mp4"
    assert (manifests / "run-att" / "s1.png").exists()
    assert (manifests / "run-att" / "v1.mp4").exists()

    manifest_files = list(manifests.glob("*.json"))
    assert manifest_files, "manifest json written"
    data = json.loads(manifest_files[0].read_text())
    atts = data["scenarios"][0]["attachments"]
    assert {"name": "shot", "type": "image/png", "path": "run-att/s1.png"} in atts
    assert {"name": "rec", "type": "video/mp4", "path": "run-att/v1.mp4"} in atts
