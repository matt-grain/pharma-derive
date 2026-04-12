# scripts/

Helper scripts for data setup, diagrams, validation, and **end-to-end testing**
of the derivation pipeline without a real LLM.

## Setup / utility

| Script | Purpose |
|---|---|
| `download_data.py` | Download CDISC Pilot Study SDTM + ADaM XPT files from the PhUSE GitHub repo into `data/` |
| `generate_diagrams.py` | Generate Mermaid `.mmd` files (FSM state diagram + orchestration sequence) into `presentation/diagrams/` |
| `validate_adam.py` | Compare a workflow's derived CSV against the CDISC ground truth ADaM XPT; reports per-variable match/mismatch stats |

Run any of these with `uv run python scripts/<name>.py`.

## End-to-end test scripts

These let you drive the full pipeline locally without hitting a real LLM API.
Each workflow spec has its own **mailbox auto-responder** that feeds canned
answers to the agents via the AgentLens mailbox, so the pipeline runs to
completion deterministically.

### Prerequisites

Three services must be running (one terminal each):

```bash
# 1) AgentLens mailbox (agents talk to this instead of a real LLM)
cd C:\Projects\AgentLens
uv run agentlens serve --mode mailbox --port 8650

# 2) CDDE backend (API + MCP server)
cd <this repo>
uv run uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload

# 3) Frontend (optional — needed if you want to click "Approve" in the UI)
cd frontend && npm run dev
```

### Auto-responders — match the responder to the spec

| Script | Answers requests for | Canned responses |
|---|---|---|
| `mailbox_simple_mock.py` | `specs/simple_mock.yaml` (AGE_GROUP, TREATMENT_DURATION, IS_ELDERLY, RISK_SCORE) | 10 |
| `mailbox_cdisc.py` | `specs/adsl_cdiscpilot01.yaml` (AGEGR1, TRTDUR, SAFFL, ITTFL, EFFFL, DISCONFL, DURDIS) | 16 |

Both print `— idle timeout 30min...` on startup and exit after 30 min with no
pending requests. Only run **one** at a time — the simple_mock responder will
return `UNKNOWN` for CDISC variables and vice versa.

```bash
# Start the responder for the spec you're about to run
PYTHONUNBUFFERED=1 uv run python scripts/mailbox_simple_mock.py
# or
PYTHONUNBUFFERED=1 uv run python scripts/mailbox_cdisc.py
```

`PYTHONUNBUFFERED=1` is only needed if you want to see the per-request
`#N: coder/AGE_GROUP -> OK` log lines in real time from a background shell.

### MCP workflow drivers

Both use the FastMCP Python client to call `run_workflow` on the backend at
`http://localhost:8000/mcp/mcp`, then poll `get_workflow_status` until the run
reaches a terminal state.

> **How this compares to clicking "New Workflow" in the UI:** the frontend
> button and these scripts both kick off a workflow via the same
> `run_workflow` tool (different transport: MCP tool call vs `POST
> /workflows/`). The UI then polls status in the background via React Query;
> the MCP drivers do their own polling loop in the terminal so you can watch
> the run advance and get the final result printed on exit. Use the frontend
> for interactive demos, the scripts for scripted/headless runs or to verify
> backend behavior (e.g. checkpointing).

| Script | What it runs | Extras |
|---|---|---|
| `mcp_run_cdisc.py` | `specs/adsl_cdiscpilot01.yaml` (7 ADSL derivations) | Polls status, prints final `get_workflow_result` |
| `mcp_test_checkpoint.py` | `specs/simple_mock.yaml` (4 derivations) | Additionally snapshots `cdde.db.workflow_states` on every poll to prove per-step checkpointing is firing. Writes a timeline JSON report to `output/mcp_checkpoint_test_<wf_id>.json` |

Typical end-to-end run (CDISC):

```bash
# Terminal A — responder (leave running)
PYTHONUNBUFFERED=1 uv run python scripts/mailbox_cdisc.py

# Terminal B — drive the workflow
uv run python scripts/mcp_run_cdisc.py
```

The workflow will advance through `parse_spec → build_dag → derive_variables`
and then park at the `human_review` HITL gate. Approve via the UI or by hand:

```bash
curl -X POST http://localhost:8000/api/v1/workflows/<id>/approve
```

Post-approval it finishes through `audit → export` and
`mcp_run_cdisc.py` prints the final result payload. To verify per-step
checkpointing in isolation, use `mcp_test_checkpoint.py` instead — it
shows how `workflow_states.updated_at` advances as each step completes.
