"""LLM repair (L2) tests: context collection, proposal parsing, path guards and
the propose/apply endpoints — the LLM itself is always mocked."""
import json
import os
from pathlib import Path
from unittest.mock import patch

import duckdb
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET", "test-secret")

import server
import services.repair as repair
from db import init_schema, NonClosingConnectionWrapper
from server import app, create_token
from services.repair import collect_context, parse_proposal, validate_target

client = TestClient(app)

RUN_ID = "repair-run-1"
STEP_FILE = "test-core/src/test/java/com/testreports/steps/UnitDemoSteps.java"


def _auth() -> dict:
    return {"Authorization": f"Bearer {create_token('admin')}"}


@pytest.fixture
def seeded_db(tmp_path):
    conn = duckdb.connect(":memory:")
    init_schema(conn)
    conn.execute(
        "INSERT INTO runs (id, version, environment, started_at) VALUES (?, 'v1', 'staging', current_timestamp)",
        [RUN_ID],
    )
    conn.execute(
        """INSERT INTO scenario_definitions (scenario_uid, identity_source, identity_key, current_name, current_feature_file, current_feature_line, doors_number)
           VALUES ('uid-trim', 'doors', 'DOORS-40002', 'Trim collapses inner whitespace (intentional failure)', 'features/unit-demo.feature', 15, 'DOORS-40002')"""
    )
    conn.execute(
        """INSERT INTO scenario_results (run_id, scenario_uid, name_at_run, status, error_message, doors_number_at_run)
           VALUES (?, 'uid-trim', 'Trim collapses inner whitespace (intentional failure)', 'FAILED',
                   'AssertionFailedError: expected: <ab> but was: <a b>', 'DOORS-40002')""",
        [RUN_ID],
    )
    conn.execute(
        """INSERT INTO worker_runs (worker_id, job_id, run_id, shard, status, tags, browser, environment)
           VALUES ('w-1', 'job-1', ?, 0, 'completed', '@UnitDemo', 'chrome', 'staging')""",
        [RUN_ID],
    )
    wrapped = NonClosingConnectionWrapper(conn)
    log_dir = Path(server.MANIFESTS_DIR) / RUN_ID
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "console.log").write_text("[ERROR] expected: <ab> but was: <a b>\nBUILD FAILURE\n")
    with patch.object(server, "get_connection", lambda read_only=False: wrapped):
        yield conn


# ── context collection ──

def test_collect_context_gathers_failure_console_and_sources(seeded_db):
    ctx = collect_context(seeded_db, RUN_ID, Path(server.MANIFESTS_DIR))
    assert ctx["target"]["scenario_uid"] == "uid-trim"
    assert "expected: <ab>" in ctx["target"]["error_message"]
    assert "BUILD FAILURE" in ctx["console_tail"]
    assert "Scenario: Trim collapses inner whitespace" in ctx["feature_source"]
    assert any("UnitDemoSteps.java" in p for p in ctx["step_sources"])


def test_context_includes_poms_architecture_and_project_map(seeded_db):
    ctx = collect_context(seeded_db, RUN_ID, Path(server.MANIFESTS_DIR))
    assert "test-core/pom.xml" in ctx["pom_sources"]
    assert "pom.xml" in ctx["pom_sources"]
    assert "WebDriverFactory" in ctx["architecture"]  # docs/TEST_MIMARISI.md
    assert "com/testreports/steps/UnitDemoSteps.java" in ctx["project_map"]
    assert "features/unit-demo.feature" in ctx["project_map"]
    # everything reaches the prompt
    user_msg = repair.build_messages(ctx)[1]["content"]
    for chunk in ("Architecture brief", "Maven poms (READ-ONLY)", "Project file map"):
        assert chunk in user_msg


def test_stack_trace_pulls_implicated_project_sources(seeded_db):
    seeded_db.execute(
        """UPDATE scenario_results SET error_message =
           'org.openqa.selenium.SessionNotCreatedException: boom
        at com.testreports.config.WebDriverFactory.createChromeDriver(WebDriverFactory.java:58)
        at com.testreports.steps.LoginSteps.user_is_on_the_login_page(LoginSteps.java:24)'
           WHERE run_id = ?""",
        [RUN_ID],
    )
    ctx = collect_context(seeded_db, RUN_ID, Path(server.MANIFESTS_DIR))
    assert any("WebDriverFactory.java" in p for p in ctx["trace_sources"])
    assert any("LoginSteps.java" in p for p in ctx["trace_sources"])


def test_class_references_in_steps_pull_custom_helpers():
    # LoginSteps calls com.testreports.config.WebDriverFactory and
    # com.testreports.allure.WebDriverHolder with fully-qualified names —
    # the one-hop expansion must surface those custom classes.
    login_steps = (repair.STEPS_DIR / "com/testreports/steps/LoginSteps.java").read_text()
    found = repair._referenced_class_sources([login_steps], already=set())
    assert any("WebDriverFactory.java" in p for p in found)
    assert any("WebDriverHolder.java" in p for p in found)


# ── proposal parsing ──

def test_parse_proposal_accepts_fenced_json():
    raw = '```json\n{"file": "a.java", "new_content": "x", "explanation": "fix"}\n```'
    assert parse_proposal(raw)["file"] == "a.java"


def test_parse_proposal_accepts_needs_human_handoff():
    parsed = parse_proposal('{"needs_human": true, "explanation": "pom dependency conflict"}')
    assert parsed == {"needs_human": True, "explanation": "pom dependency conflict"}


def test_propose_returns_needs_human_without_target_validation(seeded_db):
    reply = json.dumps({"needs_human": True, "explanation": "selenium version mismatch in pom"})
    with patch.object(server.llm_client, "is_configured", return_value=True), \
         patch.object(server.llm_client, "chat", return_value=reply):
        response = client.post(f"/api/repair/{RUN_ID}/propose", headers=_auth(), json={})
    assert response.status_code == 200
    assert response.json()["proposal"]["needs_human"] is True


def test_parse_proposal_rejects_non_json_and_missing_fields():
    with pytest.raises(ValueError, match="JSON değil"):
        parse_proposal("I think you should fix the trim step.")
    with pytest.raises(ValueError, match="eksik alanlar"):
        parse_proposal('{"file": "a.java"}')


# ── path guard ──

def test_validate_target_rejects_files_outside_test_sources():
    with pytest.raises(ValueError, match="test-core/src/test"):
        validate_target("fastapi-server/server.py")
    with pytest.raises(ValueError, match="test-core/src/test"):
        validate_target("../../etc/passwd")
    with pytest.raises(ValueError, match="mevcut bir dosya değil"):
        validate_target("test-core/src/test/java/com/testreports/steps/Ghost.java")
    assert validate_target(STEP_FILE).name == "UnitDemoSteps.java"


# ── endpoints ──

def test_propose_requires_llm_configuration(seeded_db):
    with patch.object(server.llm_client, "is_configured", return_value=False):
        response = client.post(f"/api/repair/{RUN_ID}/propose", headers=_auth(), json={})
    assert response.status_code == 503


def test_propose_returns_validated_proposal(seeded_db):
    reply = json.dumps({"file": STEP_FILE, "new_content": "// fixed", "explanation": "trim fix"})
    with patch.object(server.llm_client, "is_configured", return_value=True), \
         patch.object(server.llm_client, "chat", return_value=reply) as chat:
        response = client.post(f"/api/repair/{RUN_ID}/propose", headers=_auth(), json={})
    assert response.status_code == 200
    data = response.json()
    assert data["proposal"]["file"] == STEP_FILE
    assert data["scenario_uid"] == "uid-trim"
    # the model saw the real failure context
    sent = chat.call_args.args[0]
    assert any("expected: <ab>" in m["content"] for m in sent)


def test_propose_rejects_proposal_outside_test_sources(seeded_db):
    reply = json.dumps({"file": "fastapi-server/server.py", "new_content": "evil"})
    with patch.object(server.llm_client, "is_configured", return_value=True), \
         patch.object(server.llm_client, "chat", return_value=reply):
        response = client.post(f"/api/repair/{RUN_ID}/propose", headers=_auth(), json={})
    assert response.status_code == 422


def test_apply_rejects_files_outside_test_sources(seeded_db):
    response = client.post(
        f"/api/repair/{RUN_ID}/apply",
        headers=_auth(),
        json={"file": "fastapi-server/server.py", "new_content": "evil", "rerun": False},
    )
    assert response.status_code == 400


def test_apply_writes_file_and_reruns_original_tags(seeded_db, tmp_path, monkeypatch):
    # Route the ALLOWED_ROOT to a sandbox so the real repo sources stay untouched.
    sandbox = tmp_path / "test-core" / "src" / "test" / "java"
    sandbox.mkdir(parents=True)
    target = sandbox / "Steps.java"
    target.write_text("// broken")
    monkeypatch.setattr(repair, "ALLOWED_ROOT", tmp_path / "test-core" / "src" / "test")

    spawned = []
    monkeypatch.setattr(server, "_spawn_run", lambda run_id, options, output_dir: spawned.append((run_id, options.tags)))

    response = client.post(
        f"/api/repair/{RUN_ID}/apply",
        headers=_auth(),
        json={"file": str(target), "new_content": "// fixed", "rerun": True},
    )
    assert response.status_code == 200
    assert target.read_text() == "// fixed"
    data = response.json()
    assert data["rerun"]["job_id"].startswith("job-")
    assert spawned and spawned[0][1] == "@UnitDemo"
