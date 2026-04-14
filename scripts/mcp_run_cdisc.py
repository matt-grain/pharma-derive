"""One-shot MCP client — starts the CDISC cdiscpilot01 workflow via FastMCP.

Uses the FastMCP Python client to call run_workflow, then polls get_workflow_status
until the workflow reaches a terminal state (completed, failed, or review).
"""

from __future__ import annotations

import asyncio
import json
import sys
import time

from fastmcp import Client

MCP_URL = "http://localhost:8000/mcp/mcp"
SPEC = "specs/adsl_cdiscpilot01.yaml"


async def main() -> int:
    async with Client(MCP_URL) as client:
        print(f"[{time.strftime('%H:%M:%S')}] Connected to MCP at {MCP_URL}")
        tools = await client.list_tools()
        print(f"  tools available: {[t.name for t in tools]}")

        print(f"[{time.strftime('%H:%M:%S')}] Calling run_workflow(spec_path={SPEC!r})")
        result = await client.call_tool("run_workflow", {"spec_path": SPEC})
        payload = result.data if hasattr(result, "data") else result.content[0].text
        if isinstance(payload, str):
            payload = json.loads(payload)
        print(f"  -> {payload}")
        wf_id = payload["workflow_id"]

        last_status = ""
        for _ in range(240):  # ~8 minutes at 2s poll
            await asyncio.sleep(2)
            status_result = await client.call_tool("get_workflow_status", {"workflow_id": wf_id})
            status_payload = status_result.data if hasattr(status_result, "data") else status_result.content[0].text
            if isinstance(status_payload, str):
                status_payload = json.loads(status_payload)
            state = status_payload.get("status", "unknown")
            derived = status_payload.get("derived_variables", [])
            if state != last_status:
                print(f"[{time.strftime('%H:%M:%S')}] status={state:20s} derived={len(derived)} vars={derived}")
                last_status = state
            if state in {"completed", "failed"}:
                break
            if state == "review":
                print("  [HITL gate hit — workflow paused at review state]")
                # keep polling — external approver (curl or UI) will release

        print(f"\n[{time.strftime('%H:%M:%S')}] Fetching final result")
        try:
            final = await client.call_tool("get_workflow_result", {"workflow_id": wf_id})
            final_payload = final.data if hasattr(final, "data") else final.content[0].text
            if isinstance(final_payload, str):
                final_payload = json.loads(final_payload)
            print(json.dumps(final_payload, indent=2, default=str)[:2000])
        except Exception as exc:
            print(f"  get_workflow_result error: {exc}")

        return 0 if last_status == "completed" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
