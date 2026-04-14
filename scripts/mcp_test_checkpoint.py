"""MCP checkpoint test — runs simple_mock and captures workflow_states DB snapshots during the run.

Proves per-step checkpointing: workflow_states should receive rows as steps complete,
not only at terminal state.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
import time
from pathlib import Path

from fastmcp import Client

MCP_URL = "http://localhost:8000/mcp/mcp"
SPEC = "specs/simple_mock.yaml"
DB_PATH = Path(__file__).parent.parent / "cdde.db"
POLL_INTERVAL_S = 1.0
POLL_TIMEOUT_S = 600  # 10 min — simple_mock should finish in <3 min


def snapshot_db(wf_id: str) -> tuple[int, str | None, str | None]:
    """Return (row_count_for_wf_id, fsm_state, updated_at_iso). All None/0 if missing."""
    con = sqlite3.connect(str(DB_PATH))
    try:
        cur = con.execute(
            "SELECT fsm_state, updated_at FROM workflow_states WHERE workflow_id = ?",
            (wf_id,),
        )
        row = cur.fetchone()
        if row is None:
            return (0, None, None)
        return (1, row[0], row[1])
    finally:
        con.close()


async def main() -> int:
    timeline: list[dict[str, object]] = []
    async with Client(MCP_URL) as client:
        ts_start = time.strftime("%H:%M:%S")
        print(f"[{ts_start}] Connected to MCP at {MCP_URL}")
        tools = await client.list_tools()
        print(f"  tools: {[t.name for t in tools]}")

        print(f"[{time.strftime('%H:%M:%S')}] Starting workflow (spec={SPEC})")
        result = await client.call_tool("run_workflow", {"spec_path": SPEC})
        payload = result.data if hasattr(result, "data") else json.loads(result.content[0].text)
        if isinstance(payload, str):
            payload = json.loads(payload)
        wf_id = payload["workflow_id"]
        print(f"  wf_id={wf_id}")

        last_logged = ""
        deadline = time.monotonic() + POLL_TIMEOUT_S
        while time.monotonic() < deadline:
            await asyncio.sleep(POLL_INTERVAL_S)

            status_result = await client.call_tool("get_workflow_status", {"workflow_id": wf_id})
            sp = status_result.data if hasattr(status_result, "data") else json.loads(status_result.content[0].text)
            if isinstance(sp, str):
                sp = json.loads(sp)
            fsm_state = sp.get("status", "unknown")
            derived_count = len(sp.get("derived_variables", []))

            db_rows, db_fsm, db_updated_at = snapshot_db(wf_id)
            ts = time.strftime("%H:%M:%S")
            line = f"api_fsm={fsm_state:18s} db_rows={db_rows} db_fsm={db_fsm or '-':18s} derived={derived_count}"
            if line != last_logged:
                print(f"[{ts}] {line}")
                timeline.append(
                    {
                        "ts": ts,
                        "api_fsm_state": fsm_state,
                        "db_row_present": db_rows == 1,
                        "db_fsm_state": db_fsm,
                        "db_updated_at": db_updated_at,
                        "derived_count": derived_count,
                    }
                )
                last_logged = line

            if fsm_state in {"completed", "failed"}:
                break

        # Final payload
        print(f"\n[{time.strftime('%H:%M:%S')}] Fetching final result")
        final_payload: object | None = None
        try:
            final = await client.call_tool("get_workflow_result", {"workflow_id": wf_id})
            final_payload = final.data if hasattr(final, "data") else json.loads(final.content[0].text)
            if isinstance(final_payload, str):
                final_payload = json.loads(final_payload)
        except Exception as exc:
            print(f"  get_workflow_result error: {exc}")
            final_payload = {"error": str(exc)}

        # Persist test report
        report = {
            "spec": SPEC,
            "workflow_id": wf_id,
            "started_at": ts_start,
            "timeline": timeline,
            "final_result": final_payload,
        }
        report_path = Path(__file__).parent.parent / "output" / f"mcp_checkpoint_test_{wf_id}.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"  report written to {report_path}")

        return 0 if timeline and timeline[-1]["api_fsm_state"] == "completed" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
