# Smoke Test Plan — Post `/fix-review` (2026-04-12)

**Purpose:** After 13 fix units across domain, engine, API, and frontend, verify that no functional regressions were introduced. The automated gate is green (234 tests, 0 ruff/pyright/lint-imports errors) but tests don't cover UI interactions, the real FastMCP handshake, or end-to-end workflow orchestration under a live LLM.

**Scope:** Manual + semi-automated verification of the golden path and the specific code paths touched by each fix unit.

## Prerequisites

- [ ] `ANTHROPIC_API_KEY` set in `.env` (real Claude calls)
- [ ] SDTM inputs present under `data/sdtm/` (CDISC pilot XPT files)
- [ ] Ground truth present under `data/adam/` (for post-run diff check)
- [ ] No existing `output/` directory from prior runs (or archive it) — `mv output output.prev`
- [ ] `cdde.db` either fresh or a known-good snapshot — `rm cdde.db` for a clean slate
- [ ] Docker + Docker Compose OR Python 3.13 + Node 20 + `uv`

## Environment Options

### Option A — Docker Compose (production-like)
```bash
docker compose up --build
# backend on :8000, frontend on :5173, nginx on :80
```

### Option B — Native dev (faster iteration)
```bash
# Terminal 1
uv run uvicorn src.api.app:app --reload --port 8000

# Terminal 2
cd frontend && pnpm dev  # :5173
```

## Test Matrix

Each scenario maps to one or more fix units. `FU` column = Fix Unit ID from `FIX_PLAN.md`.

### Scenario 1 — Backend startup & import sanity

| # | Check | FU | Expected |
|---|-------|----|----------|
| 1.1 | `uv run python -c "from src.api.app import app; print('ok')"` | 1.2 | Prints `ok`, no ImportError for `DerivationOrchestrator` / `WorkflowFSM` / `orchestrator_helpers` |
| 1.2 | `uv run python -c "from src.domain.models import WorkflowStep; print(WorkflowStep.RUNNING, WorkflowStep.UNKNOWN)"` | 1.1, 1.4 | Prints `WorkflowStep.RUNNING WorkflowStep.UNKNOWN` (re-export works, new members exist) |
| 1.3 | `uv run python -c "from src.engine.debug_runner import apply_series_to_df, build_run_result; print('ok')"` | 2.1, cleanup | Prints `ok` (public names, not underscore-prefixed) |
| 1.4 | `uv run python -c "from src.api.workflow_serializer import serialize_ctx, build_result, HistoricState; print('ok')"` | 2.2 | Prints `ok` |
| 1.5 | `uv run uvicorn src.api.app:app --port 8000` — observe startup logs | all | No warnings about missing modules, dead imports, or circular dependencies |
| 1.6 | `curl http://localhost:8000/health` | — | `200 OK` with health payload |
| 1.7 | `curl http://localhost:8000/docs` | — | Swagger UI loads, lists all endpoints, schemas resolve |

### Scenario 2 — Frontend build & visual regression

| # | Check | FU | Expected |
|---|-------|----|----------|
| 2.1 | `cd frontend && pnpm tsc --noEmit` | 2.3 | Zero new errors (pre-existing TS5101 / PipelineView TS18048 acceptable) |
| 2.2 | `cd frontend && pnpm build` | 2.3 | Build succeeds |
| 2.3 | Visit `http://localhost:5173` — Dashboard | — | Renders workflow list, no console errors |
| 2.4 | Open any workflow — observe `WorkflowDetailPage` | 2.3 | Header (breadcrumb + title + approval banner) renders identically to pre-refactor, Tabs render identically, no layout shift |
| 2.5 | Check browser DevTools console | 2.3 | Zero errors, zero warnings from the refactored components |
| 2.6 | Open `SpecsPage` and click a spec | — | YAML viewer displays content |
| 2.7 | Open `AuditPage` | — | Audit records list renders |

### Scenario 3 — End-to-end workflow (golden path)

This is the full derivation flow. Run a workflow for `clinical_derivation.yaml` on CDISC pilot data.

| # | Step | FU Touched | Expected |
|---|------|-----------|----------|
| 3.1 | `POST /api/v1/workflows/` with `{"study_name": "CDISCPILOT", "spec_path": "specs/clinical_derivation.yaml"}` | 1.4 | `201` with `status: "running"` (enum member, not raw string) |
| 3.2 | `GET /api/v1/workflows/{id}` — poll until status reaches `review` | 0.5, 1.4 | Status progresses: `running` → `parsing_spec` → `deriving` → `review` |
| 3.3 | Open the workflow in the UI — verify amber "Awaiting Approval" banner appears | 2.3 | Banner visible, Approve button enabled |
| 3.4 | Click Approve (or `POST /api/v1/workflows/{id}/approve`) | F08, 2.3 | Status transitions to `auditing`, banner disappears |
| 3.5 | Poll until status reaches `completed` | 0.5 | FSM transitions cleanly, no raw string artifacts in state |
| 3.6 | `GET /api/v1/workflows/{id}/adam` — download ADaM output | — | CSV file with expected columns (AGEGR1, ITTFL, SAFFL, TRTDUR, EFFFL) |
| 3.7 | `uv run python scripts/validate_adam.py output/{id}_adam.csv data/adam/adsl.xpt` | — | Match rates: AGEGR1/ITTFL/SAFFL ≥99%, TRTDUR ≥98%, EFFFL ≥97% (matching prior session baseline) |
| 3.8 | `GET /api/v1/workflows/{id}/audit` | — | Audit trail with `human_approved` action, no raw `"unknown"` or `"failed"` strings |
| 3.9 | `GET /api/v1/workflows/{id}/dag` | — | DAG nodes returned with rule/code/QC verdict/approval state |

### Scenario 4 — Delete workflow (Fix Unit 1.3 specifically)

| # | Check | FU | Expected |
|---|-------|----|----------|
| 4.1 | `DELETE /api/v1/workflows/{id}` for the completed workflow | 1.3 | `204 No Content`, completes in <500ms |
| 4.2 | `GET /api/v1/workflows/{id}` after delete | 1.3 | `404` (workflow removed from both DB and in-memory map) |
| 4.3 | Verify `output/{id}_adam.csv` is also cleaned up | 1.3 | File gone |
| 4.4 | `cat nginx.log` or backend logs | 1.3 | No `init_db`, `session`, or `WorkflowStateRepository` traces from the router level (manager owns it now) |

### Scenario 5 — MCP server (FastMCP handshake)

| # | Check | FU | Expected |
|---|-------|----|----------|
| 5.1 | `curl -X POST http://localhost:8000/mcp/mcp -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'` | — | Lists MCP tools: `get_workflow_status`, etc. |
| 5.2 | Call `get_workflow_status` with an unknown `workflow_id` | 1.4 | Returns `status: "unknown"` (from `WorkflowStep.UNKNOWN.value`, not raw literal) |
| 5.3 | Call `get_workflow_status` with a real workflow mid-run | 1.4 | Returns actual FSM state, no raw literal fallback |

### Scenario 6 — HITL approval gate regression

| # | Check | FU | Expected |
|---|-------|----|----------|
| 6.1 | Start a new workflow, do NOT approve | F08 | Workflow stays in `review` indefinitely (asyncio.Event not set) |
| 6.2 | UI shows amber banner, Approve button enabled | 2.3 | Visual check |
| 6.3 | Approve via UI | F08, 2.3 | Immediately transitions, banner gone, tabs show derived data |
| 6.4 | Try to `POST /approve` on a workflow that's NOT in `review` state | — | Graceful error (400 or similar), no crash |

### Scenario 7 — Import/linter sanity (no new dead code)

| # | Check | FU | Expected |
|---|-------|----|----------|
| 7.1 | `grep -rn "DerivationOrchestrator\|WorkflowFSM\|orchestrator_helpers" src/ tests/` | 1.2 | Zero matches (except string mentions in docstrings/comments, flagged for review) |
| 7.2 | `grep -rn '"running"\|"unknown"\|"failed"' src/api/ src/engine/pipeline_fsm.py` | 0.5, 1.4 | Zero matches in status-assignment positions |
| 7.3 | `uv run lint-imports` | 0.3, 1.3 | 21 contracts kept, 0 broken |
| 7.4 | `uv run python tools/pre_commit_checks/check_enum_discipline.py` | 0.5, 1.4 | 53 files, 0 violations |

## Tracking

For each scenario, mark results inline:
- ✅ Pass
- ⚠️ Pass with note (e.g., visual minor difference)
- ❌ Fail — include the observation and whether to roll back the fix unit

## Rollback Triggers

If any of these fail, consider rollback of the corresponding fix unit:

| Failure | Likely Cause | Rollback |
|---------|--------------|----------|
| Scenario 1.1 fails (imports broken) | Fix Unit 1.2 deleted something still referenced | Revert 1.2 |
| Scenario 2.4 visual regression | Fix Unit 2.3 mis-split props | Revert 2.3, re-plan split |
| Scenario 3.5 stuck in raw-string state | Fix Unit 0.5 or 1.4 introduced enum mismatch | Revert the specific fix |
| Scenario 4.2 workflow still visible after delete | Fix Unit 1.3 broke session commit path | Revert 1.3 |
| Scenario 3.7 ADaM match rate drops | Unlikely to be caused by any fix unit — investigate as potential regression in agent prompts or derivation runner |

## Post-Test Actions

- [ ] Record outcomes inline
- [ ] If all green: proceed to `/validate-review` and merge
- [ ] If any failures: open issues, fix or rollback, re-run the affected scenarios
