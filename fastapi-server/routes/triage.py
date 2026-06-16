"""Triage routes (state, auto-match, jira-create/link, override), split out of
server.py. Triage models live here; shared state referenced as server.X."""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

import server

router = APIRouter()


class TriageScenarioState(BaseModel):
    scenario_uid: str
    scenario_name: str
    status: str
    error_message: Optional[str] = None
    doors_number: Optional[str] = None
    jira_keys: List[str] = []
    triage_decision: Optional[str] = None
    triage_reason: Optional[str] = None
    triage_actor: Optional[str] = None
    triage_timestamp: Optional[str] = None
    is_flaky: bool = False
    retry_attempt: int = 1


class TriageStateResponse(BaseModel):
    run_id: str
    total_failed: int
    scenarios: List[TriageScenarioState]


class OverrideRequest(BaseModel):
    decision: str
    reason: str


class LinkJiraRequest(BaseModel):
    jira_key: str


@router.get("/api/triage/{run_id}", response_model=TriageStateResponse, dependencies=[Depends(server.verify_token)])
def get_triage_state(run_id: str):
    conn = server.get_connection(read_only=True)
    try:
        rows = conn.execute("""
            SELECT
                sr.scenario_uid,
                COALESCE(sd.current_name, sr.name_at_run) as scenario_name,
                sr.status,
                sr.error_message,
                COALESCE(sr.doors_number_at_run, sd.doors_number) as doors_number,
                (SELECT string_agg(jm.jira_key, ',') FROM jira_mappings jm WHERE jm.scenario_uid = sr.scenario_uid) as jira_keys,
                td.decision as triage_decision,
                td.reason as triage_reason,
                td.actor as triage_actor,
                td.timestamp as triage_timestamp,
                sr.retry_attempt
            FROM scenario_results sr
            LEFT JOIN scenario_definitions sd ON sr.scenario_uid = sd.scenario_uid
            LEFT JOIN triage_decisions td ON sr.scenario_uid = td.scenario_uid
            WHERE sr.run_id = ? AND sr.status IN ('FAILED', 'BROKEN')
            ORDER BY sr.id
        """, [run_id]).fetchall()
        if not rows:
            run_exists = conn.execute("SELECT 1 FROM runs WHERE id = ?", [run_id]).fetchone()
            if not run_exists:
                raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

        flaky_uids = set()
        uid_counts: dict[str, int] = {}
        for row in rows:
            uid = row[0] or ""
            uid_counts[uid] = uid_counts.get(uid, 0) + 1
        for uid, count in uid_counts.items():
            if count > 1:
                flaky_uids.add(uid)

        scenarios = [
            TriageScenarioState(
                scenario_uid=row[0] or "",
                scenario_name=row[1] or "",
                status=row[2] or "UNKNOWN",
                error_message=row[3],
                doors_number=row[4],
                jira_keys=[k for k in (row[5] or "").split(",") if k],
                triage_decision=row[6],
                triage_reason=row[7],
                triage_actor=row[8],
                triage_timestamp=str(row[9]) if row[9] else None,
                is_flaky=(row[0] or "") in flaky_uids,
                retry_attempt=row[10] if row[10] else 1,
            )
            for row in rows
        ]
        return TriageStateResponse(run_id=run_id, total_failed=len(scenarios), scenarios=scenarios)
    finally:
        conn.close()


@router.post("/api/triage/{run_id}/auto-match-jira", dependencies=[Depends(server.verify_token)])
def auto_match_jira(run_id: str) -> dict:
    """For each failed scenario with a DOORS number, search Jira for existing issues and auto-link."""
    if not server.jira_client.is_configured():
        return {"matched": 0, "details": [], "skipped_reason": "Jira not configured"}

    conn = server.get_connection(read_only=False)
    try:
        server.init_schema(conn)
        rows = conn.execute("""
            SELECT sr.scenario_uid, sr.name_at_run,
                   COALESCE(sr.doors_number_at_run, sd.doors_number) AS doors_number
            FROM scenario_results sr
            LEFT JOIN scenario_definitions sd ON sr.scenario_uid = sd.scenario_uid
            WHERE sr.run_id = ? AND sr.status IN ('FAILED', 'BROKEN')
              AND COALESCE(sr.doors_number_at_run, sd.doors_number) IS NOT NULL
              AND COALESCE(sr.doors_number_at_run, sd.doors_number) != ''
        """, [run_id]).fetchall()

        INACTIVE_STATUSES = {"done", "closed", "resolved", "cancelled", "wont fix", "won't fix", "duplicate", "rejected"}

        matched = 0
        details = []
        for scenario_uid, scenario_name, doors_number in rows:
            existing_decision = conn.execute(
                "SELECT actor FROM triage_decisions WHERE scenario_uid = ? LIMIT 1",
                [scenario_uid],
            ).fetchone()
            if existing_decision and existing_decision[0] != "auto-match":
                continue

            try:
                issues = server.jira_client.search_by_doors_number(doors_number)
            except Exception:
                continue

            active_issues = [i for i in issues if i.get("status", "").lower() not in INACTIVE_STATUSES]
            if not active_issues:
                continue

            linked_keys = []
            for issue in active_issues:
                jira_key = issue["key"]
                conn.execute(
                    "INSERT OR IGNORE INTO jira_mappings (scenario_uid, doors_id, jira_key, created_at) VALUES (?, ?, ?, ?)",
                    [scenario_uid, doors_number, jira_key, datetime.now()],
                )
                linked_keys.append(jira_key)

            conn.execute(
                """INSERT OR REPLACE INTO triage_decisions
                   (scenario_uid, decision, reason, actor, timestamp)
                   VALUES (?, 'jira_linked', ?, 'auto-match', ?)""",
                [scenario_uid, f"Auto-matched by DOORS number {doors_number}: {', '.join(linked_keys)}", datetime.now()],
            )
            matched += 1
            details.append({
                "scenario_uid": scenario_uid,
                "scenario_name": scenario_name,
                "doors_number": doors_number,
                "jira_keys": linked_keys,
                "jira_statuses": [i.get("status", "") for i in active_issues],
            })

        return {"matched": matched, "details": details}
    finally:
        conn.close()


@router.post("/api/triage/{run_id}/scenarios/{scenario_id}/jira", response_model=server.JiraResponse, status_code=201, dependencies=[Depends(server.verify_token)])
def create_triage_jira(run_id: str, scenario_id: str, response: Response, _: server.TokenData = Depends(server.verify_token)):
    conn = server.get_connection(read_only=False)
    try:
        server.init_schema(conn)
        row = conn.execute("""
            SELECT sr.scenario_uid, sr.name_at_run, sr.error_message, sr.doors_number_at_run,
                   sd.current_name, sd.current_feature_file, sd.current_feature_line,
                   sr.screenshot_path, sr.video_path
            FROM scenario_results sr
            LEFT JOIN scenario_definitions sd ON sr.scenario_uid = sd.scenario_uid
            WHERE sr.run_id = ? AND sr.scenario_uid = ?
        """, [run_id, scenario_id]).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found in run '{run_id}'")

        existing = conn.execute(
            "SELECT jira_key FROM jira_mappings WHERE scenario_uid = ? LIMIT 1", [scenario_id]
        ).fetchone()
        if existing:
            response.status_code = 200
            return server.JiraResponse(jiraKey=existing[0], jiraUrl=server.jira_client.issue_url(existing[0]))

        scenario_uid, name_at_run, error_message, doors_number = row[0], row[1], row[2], row[3]
        scenario_name = row[4] or name_at_run
        screenshot_path = row[7]
        video_path = row[8]
        run_version = (conn.execute("SELECT version FROM runs WHERE id=?", [run_id]).fetchone() or [None])[0]

        if not server.jira_client.is_configured():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Jira integration not configured. Set JIRA_BASE_URL, JIRA_PAT, JIRA_PROJECT.",
            )

        summary = f"Automated test failed: {scenario_name}"
        step_rows = conn.execute(
            "SELECT name_at_run, status FROM scenario_results WHERE run_id=? AND scenario_uid=? ORDER BY id",
            [run_id, scenario_id],
        ).fetchall()
        step_lines = "\n".join(
            f"  [FAIL] {r[0]}" if str(r[1]).upper() in ("FAILED", "BROKEN") else f"  [pass] {r[0]}"
            for r in step_rows
        )
        description = server.build_jira_description(
            run_id=run_id,
            scenario_name=scenario_name,
            doors_number=doors_number,
            version=run_version,
            error_message=error_message,
            step_lines=step_lines,
        )

        try:
            issue = server.jira_client.create_issue(summary, description, doors_number)
            key = issue["key"] if isinstance(issue, dict) else issue
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Jira error: {str(exc)}")

        conn.execute("""
            INSERT OR IGNORE INTO jira_mappings (scenario_uid, doors_id, jira_key, created_at)
            VALUES (?, ?, ?, current_timestamp)
        """, [scenario_id, doors_number, key])

        now = datetime.now()
        conn.execute("""
            INSERT INTO triage_decisions (scenario_uid, run_id, decision, actor, timestamp)
            VALUES (?, ?, 'jira_created', 'engineer', ?)
            ON CONFLICT (scenario_uid) DO UPDATE SET
                decision = 'jira_created', actor = 'engineer', timestamp = ?
        """, [scenario_id, run_id, now, now])

        if doors_number:
            server.update_scenario_history_explanation(conn, doors_number, run_id, key)

        for fpath in [screenshot_path, video_path]:
            if fpath:
                full = (server.MANIFESTS_DIR / fpath).resolve()
                if full.exists() and str(full).startswith(str(server.MANIFESTS_DIR.resolve())):
                    try:
                        server.jira_client.attach_screenshot(key, str(full))
                    except Exception:
                        pass

        return server.JiraResponse(jiraKey=key, jiraUrl=server.jira_client.issue_url(key))
    finally:
        conn.close()


@router.post("/api/triage/{run_id}/scenarios/{scenario_id}/override", response_model=dict, status_code=200, dependencies=[Depends(server.verify_token)])
def override_scenario(run_id: str, scenario_id: str, req: OverrideRequest, token: server.TokenData = Depends(server.verify_token)):
    if not req.reason or not req.reason.strip():
        raise HTTPException(status_code=422, detail="Reason is required and cannot be empty")
    if req.decision not in ("accepted_pass", "accepted_skip"):
        raise HTTPException(status_code=422, detail="Decision must be 'accepted_pass' or 'accepted_skip'")

    conn = server.get_connection(read_only=False)
    try:
        server.init_schema(conn)
        row = conn.execute("""
            SELECT scenario_uid, status FROM scenario_results
            WHERE run_id = ? AND scenario_uid = ?
        """, [run_id, scenario_id]).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found in run '{run_id}'")

        previous_status = row[1]
        actor = token.username
        now = datetime.now()

        conn.execute("""
            INSERT INTO override_audit (scenario_uid, previous_status, new_decision, reason, actor, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, [scenario_id, previous_status, req.decision, req.reason.strip(), actor, now])

        conn.execute("""
            INSERT INTO triage_decisions (scenario_uid, run_id, decision, actor, reason, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (scenario_uid) DO UPDATE SET
                decision = ?, actor = ?, reason = ?, timestamp = ?
        """, [scenario_id, run_id, req.decision, actor, req.reason.strip(), now,
              req.decision, actor, req.reason.strip(), now])

        return {"success": True, "scenario_uid": scenario_id, "decision": req.decision}
    finally:
        conn.close()


@router.post("/api/triage/{run_id}/scenarios/{scenario_id}/link-jira", response_model=server.JiraResponse, status_code=200, dependencies=[Depends(server.verify_token)])
def link_jira_issue(run_id: str, scenario_id: str, req: LinkJiraRequest, _: server.TokenData = Depends(server.verify_token)):
    jira_key = req.jira_key.strip()
    if not jira_key:
        raise HTTPException(status_code=422, detail="jira_key is required")

    conn = server.get_connection(read_only=False)
    try:
        server.init_schema(conn)
        row = conn.execute("""
            SELECT sr.scenario_uid, sr.doors_number_at_run
            FROM scenario_results sr
            WHERE sr.run_id = ? AND sr.scenario_uid = ?
        """, [run_id, scenario_id]).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found in run '{run_id}'")

        doors_number = row[1]

        existing = conn.execute("""
            SELECT 1 FROM jira_mappings WHERE scenario_uid = ? AND jira_key = ?
        """, [scenario_id, jira_key]).fetchone()
        if existing:
            return server.JiraResponse(jiraKey=jira_key, jiraUrl=server.jira_client.issue_url(jira_key))

        conn.execute("""
            INSERT INTO jira_mappings (scenario_uid, doors_id, jira_key, created_at)
            VALUES (?, ?, ?, ?)
        """, [scenario_id, doors_number, jira_key, datetime.now()])

        conn.execute("""
            INSERT INTO triage_decisions (scenario_uid, run_id, decision, actor, timestamp)
            VALUES (?, ?, 'jira_linked', 'engineer', ?)
            ON CONFLICT (scenario_uid) DO UPDATE SET
                decision = 'jira_linked', actor = 'engineer', timestamp = ?
        """, [scenario_id, run_id, datetime.now(), datetime.now()])

        if doors_number:
            server.update_scenario_history_explanation(conn, doors_number, run_id, jira_key)

        return server.JiraResponse(jiraKey=jira_key, jiraUrl=server.jira_client.issue_url(jira_key))
    finally:
        conn.close()
