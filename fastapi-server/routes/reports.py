"""Report-merge, public-share and CSV-export routes, split out of server.py.

Reports-specific helpers/model (_SHARE_ROW_SELECT, _share_blockers,
_fetch_share_rows, GenerateShareRequest) live here; shared server state is
referenced as server.X, pure services imported directly.
"""
import json
from datetime import datetime, timezone
from typing import List
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel

import server
from models import PublicReportSnapshot
from services.identifiers import extract_doors_id
from services.csv_export import doors_csv_row, doors_csv_document

router = APIRouter()


@router.get("/api/reports/merge-data", dependencies=[Depends(server.verify_token)])
async def reports_merge_data(run_ids: str = ""):
    """Return merged scenario data for selected run IDs (comma-separated)."""
    if not run_ids:
        return {"runs": [], "scenarios": [], "summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0}}
    ids = [r.strip() for r in run_ids.split(",") if r.strip()]
    manifests = server.load_manifests()
    selected = [m for m in manifests if m.runId in ids]

    uid_map: dict[tuple[str, int], str] = {}
    try:
        conn = server.get_connection(read_only=False)
        server.init_schema(conn)
        placeholders = ",".join(["?"] * len(ids))
        uid_rows = conn.execute(
            f"""
            SELECT run_id, scenario_uid,
                   ROW_NUMBER() OVER (PARTITION BY run_id ORDER BY rowid) - 1 AS pos
            FROM scenario_results
            WHERE run_id IN ({placeholders})
            """,
            ids,
        ).fetchall()
        conn.close()
        uid_map = {(r[0], int(r[2])): r[1] for r in uid_rows}
    except Exception:
        pass

    all_scenarios = []
    for m in selected:
        for i, s in enumerate(m.scenarios):
            all_scenarios.append({
                "runId": m.runId,
                "id": s.id,
                "scenario_uid": uid_map.get((m.runId, i)),
                "name": s.name,
                "status": s.status,
                "duration": s.duration,
                "tags": s.tags,
                "steps": [{"name": st.name, "status": st.status, "errorMessage": st.errorMessage} for st in s.steps],
                "errorMessage": s.steps[0].errorMessage if s.steps and s.status == "failed" and any(st.errorMessage for st in s.steps) else None,
            })
    summary = {
        "total": len(all_scenarios),
        "passed": sum(1 for s in all_scenarios if s["status"] == "passed"),
        "failed": sum(1 for s in all_scenarios if s["status"] == "failed"),
        "skipped": sum(1 for s in all_scenarios if s["status"] == "skipped"),
    }
    return {"runs": [{"runId": m.runId, "timestamp": str(m.timestamp), "totalScenarios": m.totalScenarios, "passed": m.passed, "failed": m.failed, "skipped": m.skipped} for m in selected], "scenarios": all_scenarios, "summary": summary}


class GenerateShareRequest(BaseModel):
    scenario_ids: List[str]
    title: str = "Public Report"


# Shared SELECT for public-share scenario rows; {where} is a fixed literal clause.
_SHARE_ROW_SELECT = """
    SELECT sr.scenario_uid, sr.name_at_run, sr.status, sr.duration_seconds,
           sr.error_message, sd.current_name,
           COALESCE(sr.doors_number_at_run, sd.doors_number) AS doors_number,
           COALESCE(
               sr.jira_key_at_run,
               (SELECT jm.jira_key FROM jira_mappings jm WHERE jm.scenario_uid = sr.scenario_uid LIMIT 1),
               (SELECT bm.jira_key FROM bug_mappings bm WHERE bm.doors_number = COALESCE(sr.doors_number_at_run, sd.doors_number) LIMIT 1)
           ) AS jira_key,
           r.version,
           sr.run_id
    FROM scenario_results sr
    LEFT JOIN scenario_definitions sd ON sr.scenario_uid = sd.scenario_uid
    LEFT JOIN runs r ON sr.run_id = r.id
    WHERE {where}
    LIMIT 1
"""


def _share_blockers(conn, parsed) -> list[dict]:
    """Return untriaged-failure blockers for the selected scenarios."""
    blockers = []
    for run_id, scenario_uid, manifest_status in parsed:
        if manifest_status and manifest_status.upper() not in {"FAILED", "BROKEN"}:
            continue
        if run_id:
            status_row = conn.execute(
                "SELECT status FROM scenario_results WHERE run_id = ? AND scenario_uid = ? LIMIT 1",
                [run_id, scenario_uid],
            ).fetchone()
        else:
            status_row = conn.execute(
                "SELECT status FROM scenario_results WHERE scenario_uid = ? LIMIT 1",
                [scenario_uid],
            ).fetchone()
        if not status_row or status_row[0] not in {"FAILED", "BROKEN"}:
            continue
        triage_row = conn.execute(
            "SELECT decision FROM triage_decisions WHERE scenario_uid = ? LIMIT 1",
            [scenario_uid],
        ).fetchone()
        if not triage_row:
            blockers.append({
                "scenario_id": scenario_uid,
                "reason": "No triage decision — must be linked to Jira or accepted via override",
            })
        elif triage_row[0] not in {"jira_linked", "jira_created", "accepted_pass", "accepted_skip"}:
            blockers.append({
                "scenario_id": scenario_uid,
                "reason": f"Triage decision is '{triage_row[0]}' — must be Jira-linked or overridden",
            })
    return blockers


def _fetch_share_rows(conn, parsed) -> list:
    """Fetch the joined scenario row for each selected id."""
    rows = []
    for run_id, scenario_uid, _ in parsed:
        if run_id:
            row = conn.execute(
                _SHARE_ROW_SELECT.format(where="sr.run_id = ? AND sr.scenario_uid = ?"),
                [run_id, scenario_uid],
            ).fetchone()
        else:
            row = conn.execute(
                _SHARE_ROW_SELECT.format(where="sr.scenario_uid = ?"),
                [scenario_uid],
            ).fetchone()
        if row:
            rows.append(row)
    return rows


@router.post("/api/reports/generate-share", dependencies=[Depends(server.verify_token)])
async def generate_public_share(req: GenerateShareRequest):
    """Create a public snapshot for selected scenario IDs (engineer-only)."""
    if not req.scenario_ids:
        raise HTTPException(status_code=422, detail="scenario_ids cannot be empty")

    conn = server.get_connection(read_only=False)
    try:
        server.init_schema(conn)

        def _parse_id(raw: str):
            parts = raw.split(":", 2)
            if len(parts) == 3:
                return parts[0], parts[1], parts[2]
            if len(parts) == 2:
                return parts[0], parts[1], None
            return None, raw, None

        parsed = [_parse_id(sid) for sid in req.scenario_ids]

        blockers = _share_blockers(conn, parsed)
        if blockers:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Cannot generate public share — un triaged failures found",
                    "blockers": blockers,
                },
            )

        scenario_rows = _fetch_share_rows(conn, parsed)

        scenarios_internal = []
        csv_rows = []
        manifest_doors_by_run_name = {}
        parsed_run_ids = {run_id for run_id, _, _ in parsed if run_id}
        if parsed_run_ids:
            for manifest in server.load_manifests():
                if manifest.runId not in parsed_run_ids:
                    continue
                for scenario in manifest.scenarios:
                    for tag in scenario.tags:
                        found_doors = extract_doors_id(tag)
                        if found_doors:
                            manifest_doors_by_run_name.setdefault((manifest.runId, scenario.name), found_doors)
                            break
        passed = failed = skipped = 0
        for row in scenario_rows:
            status = row[2] or "UNKNOWN"
            if status == "PASSED":
                passed += 1
            elif status in {"FAILED", "BROKEN"}:
                failed += 1
            else:
                skipped += 1
            scenarios_internal.append({
                "id": row[0],
                "name": row[5] or row[1] or row[0],
                "status": status.lower(),
                "duration": f"PT{row[3]:.3f}S" if row[3] else "PT0S",
            })
            csv_rows.append({
                "doors_id": row[6] or manifest_doors_by_run_name.get((row[9], row[1]), ""),
                "name": row[5] or row[1] or row[0],
                "status": status,
                "jira_key": row[7] or "",
                "version": row[8] or "vX.X",
            })

        internal_report = {
            "totalScenarios": len(scenario_rows),
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "scenarios": scenarios_internal,
            "generated_timestamp": datetime.now(timezone.utc),
        }

        snapshot = PublicReportSnapshot.from_internal(internal_report)
        snapshot_payload = snapshot.model_dump(mode="json")
        snapshot_payload["_csv_export_rows"] = csv_rows
        snapshot_json = json.dumps(snapshot_payload, ensure_ascii=False)

        share_id = str(uuid4())
        conn.execute("""
            INSERT INTO public_snapshots (share_id, created_at, snapshot_data, status)
            VALUES (?, current_timestamp, ?, 'active')
        """, [share_id, snapshot_json])

        return {"share_id": share_id, "url": f"/public/reports/{share_id}"}
    finally:
        conn.close()


@router.get("/api/public/reports/{share_id}")
async def get_public_snapshot(share_id: str):
    """Return sanitized snapshot JSON (anonymous access)."""
    conn = server.get_connection(read_only=True)
    try:
        row = conn.execute(
            "SELECT snapshot_data FROM public_snapshots WHERE share_id = ? AND status = 'active'",
            [share_id],
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Snapshot not found")
        snapshot = json.loads(row[0])
        snapshot.pop("_csv_export_rows", None)
        return snapshot
    finally:
        conn.close()


@router.get("/public/reports", response_class=HTMLResponse)
async def list_public_reports():
    conn = server.get_connection(read_only=True)
    try:
        rows = conn.execute(
            "SELECT share_id, created_at, snapshot_data FROM public_snapshots WHERE status = 'active' ORDER BY created_at ASC"
        ).fetchall()

        reports = []
        trend_labels, trend_passed, trend_failed, trend_skipped = [], [], [], []
        total_passed = total_failed = total_skipped = total_scenarios = 0
        total_duration = 0.0

        for row in rows:
            try:
                snapshot = json.loads(row[2])
                summary = snapshot.get("run_summary", {})
                passed = summary.get("passed", 0) or 0
                failed = summary.get("failed", 0) or 0
                skipped = summary.get("skipped", 0) or 0
                scenarios = summary.get("total_scenarios", 0) or 0
                total_passed += passed
                total_failed += failed
                total_skipped += skipped
                total_scenarios += scenarios
                total_duration += float(snapshot.get("avg_duration", 0) or 0)

                dt = row[1]
                label = dt.strftime("%m-%d") if hasattr(dt, "strftime") else str(dt)[:10]
                trend_labels.append(label)
                trend_passed.append(passed)
                trend_failed.append(failed)
                trend_skipped.append(skipped)

                success_rate = round((passed / scenarios * 100), 1) if scenarios > 0 else 0
                reports.append({
                    "share_id": row[0],
                    "created_at": str(row[1])[:16] if row[1] else "",
                    "total_scenarios": scenarios,
                    "passed": passed,
                    "failed": failed,
                    "skipped": skipped,
                    "success_rate": success_rate,
                })
            except Exception:
                continue

        reports.reverse()
        trend_labels.reverse()
        trend_passed.reverse()
        trend_failed.reverse()
        trend_skipped.reverse()

        total_all = total_passed + total_failed + total_skipped
        success_rate = round((total_passed / total_all * 100), 1) if total_all > 0 else 0
        avg_duration = round((total_duration / len(rows)), 1) if rows else 0

        env = Environment(loader=FileSystemLoader(server.TEMPLATES_DIR))
        tpl = env.get_template("public_reports.html")
        html = tpl.render(
            reports=reports,
            success_rate=success_rate,
            total_scenarios=total_scenarios,
            avg_duration=avg_duration,
            total_passed=total_passed,
            total_failed=total_failed,
            total_skipped=total_skipped,
            trend_labels=trend_labels,
            trend_passed=trend_passed,
            trend_failed=trend_failed,
            trend_skipped=trend_skipped,
        )
        return HTMLResponse(content=html)
    finally:
        conn.close()


@router.get("/api/csv/export")
def export_csv(run_id: str, _: server.TokenData = Depends(server.verify_token_page)):
    conn = server.get_connection(read_only=True)
    try:
        rows = conn.execute(
            """
            SELECT
                COALESCE(sr.doors_number_at_run, sd.doors_number, '') AS doors_id,
                sr.status,
                COALESCE(
                    sr.jira_key_at_run,
                    (SELECT jm.jira_key FROM jira_mappings jm WHERE jm.scenario_uid = sr.scenario_uid LIMIT 1),
                    (SELECT bm.jira_key FROM bug_mappings bm WHERE bm.doors_number = COALESCE(sr.doors_number_at_run, sd.doors_number) LIMIT 1),
                    ''
                ) AS jira_key,
                COALESCE(r.version, 'vX.X') AS version,
                sr.name_at_run
            FROM scenario_results sr
            LEFT JOIN scenario_definitions sd ON sr.scenario_uid = sd.scenario_uid
            LEFT JOIN runs r ON sr.run_id = r.id
            WHERE sr.run_id = ?
            ORDER BY doors_id, sr.name_at_run
            """,
            [run_id],
        ).fetchall()

        if not rows:
            raise HTTPException(status_code=404, detail="No scenarios found for this run")

        manifest_doors_by_name = {}
        for manifest in server.load_manifests():
            if manifest.runId != run_id:
                continue
            for scenario in manifest.scenarios:
                for tag in scenario.tags:
                    found_doors = extract_doors_id(tag)
                    if found_doors:
                        manifest_doors_by_name.setdefault(scenario.name, found_doors)
                        break
            break

        csv_rows = []
        for r in rows:
            doors_id, status, jira_key, version, name = r
            doors_id = doors_id or manifest_doors_by_name.get(name, "")
            csv_rows.append(doors_csv_row(doors_id, status, jira_key, version))

        content = doors_csv_document(csv_rows)
        return Response(
            content=content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=doors_export_{run_id}.csv"},
        )
    finally:
        conn.close()


@router.get("/api/csv/share/{share_id}", dependencies=[Depends(server.verify_token)])
def export_csv_share(share_id: str):
    conn = server.get_connection(read_only=True)
    try:
        row = conn.execute(
            "SELECT snapshot_data FROM public_snapshots WHERE share_id = ? AND status = 'active'",
            [share_id],
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Snapshot not found")

        snapshot = json.loads(row[0])
        csv_export_rows = snapshot.get("_csv_export_rows") or snapshot.get("scenario_list", [])
        if not csv_export_rows:
            raise HTTPException(status_code=404, detail="No scenarios in snapshot")

        csv_rows = []
        for s in csv_export_rows:
            csv_rows.append(doors_csv_row(
                s.get("doors_id") or "",
                s.get("status") or "",
                s.get("jira_key") or "",
                s.get("version") or "vX.X",
            ))

        content = doors_csv_document(csv_rows)
        return Response(
            content=content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=report_{share_id[:8]}.csv"},
        )
    finally:
        conn.close()


@router.get("/public/reports/{share_id}", response_class=HTMLResponse)
async def render_public_report(share_id: str):
    """Render public HTML report (anonymous access; allowlisted fields only)."""
    conn = server.get_connection(read_only=True)
    try:
        row = conn.execute(
            "SELECT snapshot_data FROM public_snapshots WHERE share_id = ? AND status = 'active'",
            [share_id],
        ).fetchone()
        if not row:
            env = Environment(loader=FileSystemLoader(server.TEMPLATES_DIR))
            tpl = env.get_template("public_404.html")
            return HTMLResponse(content=tpl.render(), status_code=404)
        snapshot = json.loads(row[0])

        scenario_list = [
            {"name": s.get("name", ""), "status": s.get("status", "unknown")}
            for s in snapshot.get("scenario_list", [])
        ]

        env = Environment(loader=FileSystemLoader(server.TEMPLATES_DIR))
        tpl = env.get_template("public_report.html")
        html = tpl.render(
            title=snapshot.get("run_summary", {}).get("total_scenarios", 0),
            generated_timestamp=snapshot.get("generated_timestamp", ""),
            total_passed=snapshot.get("total_passed", 0),
            total_failed=snapshot.get("total_failed", 0),
            total_skipped=snapshot.get("total_skipped", 0),
            total_scenarios=snapshot.get("run_summary", {}).get("total_scenarios", 0),
            scenario_list=scenario_list,
        )
        return HTMLResponse(content=html)
    finally:
        conn.close()
