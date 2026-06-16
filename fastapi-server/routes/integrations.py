"""DOORS export and email-report routes, split out of server.py.

Shared helpers/state referenced as server.X (run_doors_dxl, is_doors_available,
send_email, _run_email_context, get_connection) to keep the test monkeypatch
surface intact (e.g. patch('server.send_email')).
"""
import json

from fastapi import APIRouter, Depends, HTTPException

import server

router = APIRouter()


@router.post("/api/doors/run", dependencies=[Depends(server.verify_token)])
async def doors_run(req: server.DoorsRunRequest):
    if not server.is_doors_available():
        return {"status": "unavailable", "message": "DOORS not installed"}
    code, out, err = server.run_doors_dxl(req.script)
    return {"status": "success" if code == 0 else "failed", "stdout": out, "stderr": err}


@router.post("/api/email/send", dependencies=[Depends(server.verify_token)])
async def email_send(to: str, run_id: str):
    context = server._run_email_context(run_id)
    try:
        server.send_email(to, f"Test Raporu - {run_id}", "test_report.html", context)
        return {"sent": True}
    except Exception as e:
        return {"sent": False, "error": str(e)}


@router.post("/api/doors/share/{share_id}", dependencies=[Depends(server.verify_token)])
async def doors_share_export(share_id: str):
    """Engineer-only: DOORS export for a public share snapshot."""
    conn = server.get_connection(read_only=True)
    try:
        row = conn.execute(
            "SELECT snapshot_data FROM public_snapshots WHERE share_id = ? AND status = 'active'",
            [share_id],
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Snapshot not found")
        snapshot = json.loads(row[0])

        scenario_list = snapshot.get("scenario_list", [])
        scenario_names = [s.get("name", "") for s in scenario_list if s.get("name")]
        scenario_block = "\n".join(f'  "{name}"' for name in scenario_names if name)

        dxl_script = f"""// DOORS export for public share {share_id}
// Scenarios: {len(scenario_list)}
string[] scenarios = {{{scenario_block}
}};
print("DOORS share export: " + str(scenario_list.length()) + " scenarios\\n");
"""
        if not server.is_doors_available():
            conn.close()
            return {"status": "unavailable", "message": "DOORS not installed"}
        code, out, err = server.run_doors_dxl(dxl_script)
        conn.close()
        return {"status": "success" if code == 0 else "failed", "stdout": out, "stderr": err}
    except HTTPException:
        raise
    except Exception:
        conn.close()
        raise HTTPException(status_code=500, detail="DOORS export failed")


@router.post("/api/email/share/{share_id}", dependencies=[Depends(server.verify_token)])
async def email_share_send(share_id: str, to: str):
    """Engineer-only: send email with public share link /public/reports/{share_id}."""
    conn = server.get_connection(read_only=True)
    try:
        row = conn.execute(
            "SELECT snapshot_data FROM public_snapshots WHERE share_id = ? AND status = 'active'",
            [share_id],
        ).fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Snapshot not found")
        snapshot = json.loads(row[0])
        run_summary = snapshot.get("run_summary", {})
        context = {
            "total": run_summary.get("total_scenarios", 0),
            "passed": run_summary.get("passed", 0),
            "failed": run_summary.get("failed", 0),
            "skipped": run_summary.get("skipped", 0),
            "started_at": snapshot.get("generated_timestamp", ""),
            "dashboard_url": f"/public/reports/{share_id}",
        }
        server.send_email(to, f"Test Raporu - {share_id}", "test_report.html", context)
        return {"sent": True}
    except HTTPException:
        conn.close()
        raise
    except Exception as e:
        conn.close()
        return {"sent": False, "error": str(e)}
