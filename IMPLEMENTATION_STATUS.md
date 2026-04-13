# Implementation Status — pharma-derive

**Last updated:** 2026-04-13
**Plan:** IMPLEMENTATION_PLAN.md

## Progress Summary

| Phase | Status | Tests | Completion |
|-------|--------|-------|------------|
| Phase 1: Domain layer | ✅ Complete | 25 (py) | 100% |
| Phase 2: Agent definitions | ✅ Complete | 52 (py) | 100% |
| Phase 3: Orchestration | ✅ Complete | 87 (py) | 100% |
| Phase 4: Persistence + Audit | ✅ Complete | 118 (py) | 100% |
| Phase 5: CDISC data | ✅ Complete | 125 (py) | 100% |
| Phase 6: Review fixes | ✅ Complete | 148 (py) | 100% |
| Phase 7: Streamlit UI | ✅ Complete | 148 (py) | 100% |
| Phase 8: Design doc + Presentation | ✅ Complete | 148 (py) | 100% |
| Phase 9: Docker + README | ✅ Complete | 148 (py) | 100% |
| Phase 10: Production hardening | ✅ Complete | 153 (py) | 100% |
| Phase 11: UI/API split | ✅ Complete | 173 (py) | 100% |
| Phase 12: YAML agent config | ✅ Complete | 173 (py) | 100% |
| Phase 13: ADaM data output (F07) | ✅ Complete | 189 (py) | 100% |
| Phase 14: YAML pipeline (F02/F03) | ✅ Complete | 243 (py) | 100% |
| Phase 15: Resilience + restart + lineage DAG | ✅ Complete | 259 (py) | 100% |
| Phase 16.1: Long-term memory wiring | ✅ Complete | 282 (py) | 100% |
| Phase 16.2a: HITL backend plumbing | ✅ Complete | 284 (py) | 100% |
| Phase 16.2b: HITL backend API surface | ✅ Complete | 292 (py) | 100% |
| Phase 16.3.0: Frontend test infrastructure | ✅ Complete | 0 (ts) | 100% |
| Phase 16.3a: HITL frontend plumbing | ✅ Complete | 0 (ts) | 100% |
| Phase 16.3b: HITL frontend dialogs + wiring | ✅ Complete | 13 (ts) | 100% |

**Overall:** 20/20 phases complete (100%) ✅
**Backend:** 292 tests | **Frontend:** 13 tests

---

## Phase 5 — CDISC Pilot ADSL Spec + XPT Loader

**Implemented:** 2026-04-09
**Agent:** general-purpose
**Tooling:** ✅ All pass

### Completed
- ✅ XPT format support — pyreadstat integration with multi-domain left-join merge
- ✅ ADSL spec — 7 real CDISC derivations (AGEGR1, TRTDUR, SAFFL, ITTFL, EFFFL, DISCONFL, DURDIS)
- ✅ pyreadstat version bounds fixed (>=1.3,<2)
- ✅ 3 pre-commit checks added (file-length, llm-gateway, enum-discipline)

### Files Created
- `specs/adsl_cdiscpilot01.yaml` (52 lines)
- `tests/integration/test_cdisc.py` (62 lines)
- `tools/pre_commit_checks/check_file_length.py`
- `tools/pre_commit_checks/check_llm_gateway.py`
- `tools/pre_commit_checks/check_enum_discipline.py`

### Tests Added
- 3 unit tests + 4 integration tests (+7 total)

---

## Phase 6 — Review Fix: Deferred Items

**Implemented:** 2026-04-09
**Agent:** general-purpose
**Tooling:** ✅ All pass (148 tests, 19 import contracts)

### Completed
- ✅ 6A: File splits (orchestrator, spec_parser, tools)
- ✅ 6B: AuditAction + AgentName enums, DebugContext dataclass
- ✅ 6C: 2 new import-linter contracts (19 total)
- ✅ 6D: 13 new tests, AAA markers in all 15 test files

### Files Created
- `src/engine/workflow_models.py`, `src/domain/source_loader.py`, `src/domain/synthetic.py`, `src/agents/deps.py`
- `tests/unit/test_derivation_runner.py`, `tests/unit/test_logging.py`

---

## Phase 7 — Streamlit HITL UI

**Implemented:** 2026-04-09
**Agent:** general-purpose
**Tooling:** ✅ All pass (ruff clean, pyright 0 errors, 19 import contracts, 148 tests)

### Completed
- ✅ AgentLens design system theme (dark palette, IBM Plex Mono, Playfair Display)
- ✅ Main app with sidebar navigation
- ✅ Workflow page — spec selection, LLM config, run button, results display with QC cards
- ✅ Audit trail page — run selection, variable filtering, record display, JSON export
- ✅ DAG visualization component (Graphviz DOT with status colors)
- ✅ Streamlit dependency added (>=1.40,<2)

### Files Created
- `src/ui/theme.py` (80 lines) — CSS design system + helper functions
- `src/ui/app.py` (30 lines) — entry point with sidebar navigation
- `src/ui/pages/__init__.py` (1 line)
- `src/ui/pages/workflow.py` (140 lines) — workflow page with HITL review gates
- `src/ui/pages/audit.py` (59 lines) — audit trail viewer
- `src/ui/components/__init__.py` (1 line)
- `src/ui/components/dag_view.py` (39 lines) — DAG-to-DOT converter

### Files Modified
- `pyproject.toml` — added streamlit dependency

### Verification Checklist
| Item | Status |
|------|--------|
| All files created | ✅ |
| All files under 200 lines | ✅ (max: workflow.py at 140) |
| All functions under 40 lines | ✅ |
| No raw string comparisons | ✅ (uses DerivationStatus enum for DAG colors) |
| No business logic in UI | ✅ (orchestrator handles all logic) |
| Tooling clean | ✅ |
| Import contracts pass | ✅ (19/19, including ui-no-persistence) |

---

## Phase 8 — Design Document + Presentation

**Implemented:** 2026-04-09
**Agent:** general-purpose
**Tooling:** N/A (documentation only)

### Completed
- ✅ Design document (`docs/design.md`) — 3-page synthesized deliverable with mermaid diagrams
- ✅ Marp presentation (`presentation/slides.md`) — 18 slides with speaker notes, dark theme
- ✅ Presentation README (`presentation/README.md`) — render instructions

### Files Created
- `docs/design.md` (207 lines) — system architecture, agent roles, orchestration, DAG, HITL, traceability, memory, trade-offs, limitations
- `presentation/slides.md` (352 lines) — 18 Marp slides for 15-20 min panel talk
- `presentation/README.md` (11 lines) — Marp CLI render command

---

## Phase 9 — Docker Compose + README

**Implemented:** 2026-04-09
**Agent:** general-purpose

### Completed
- ✅ Multi-stage Dockerfile (python:3.13-slim + uv from official image)
- ✅ docker-compose.yml (single service, output/data volumes, env defaults)
- ✅ .dockerignore (excludes tests, tools, .git, .venv)
- ✅ .env.example (LLM_BASE_URL, LLM_API_KEY, DATABASE_URL)
- ✅ README.md (94 lines — quick start, architecture, features, quality metrics, deliverable links)

### Files Created
- `Dockerfile` (26 lines)
- `docker-compose.yml` (13 lines)
- `.dockerignore` (18 lines)
- `.env.example` (7 lines)
- `README.md` (94 lines)

---

## Phase 13 — ADaM Data Output (F07)

**Implemented:** 2026-04-11
**Agents:** `python-fastapi` (13.1), `vite-react` (13.2)
**Tooling:** ✅ All pass (189 tests, 20 import contracts)

### Phase 13.1 — Backend: Data Preview API + Parquet Export
- ✅ 3 new API schemas: `ColumnInfo`, `DatasetPreview`, `DataPreviewResponse`
- ✅ `GET /workflows/{id}/data` — returns source SDTM + derived ADaM preview (columns, dtypes, nulls, sample rows)
- ✅ `GET /workflows/{id}/adam?format=csv|parquet` — format selection on download endpoint
- ✅ Parquet export alongside CSV in `_export_adam()` (pyarrow engine)
- ✅ Delete endpoint cleanup includes `.parquet` files
- ✅ 5 new API tests (13 total)

### Phase 13.2 — Frontend: Data Tab + UI Polish
- ✅ `DataTab.tsx` — collapsible schema grid, sticky table headers, row numbers, alternating stripes, row count footer
- ✅ Color-coded dtype badges (int64=blue, float64=violet, object=gray, bool=amber)
- ✅ Export toolbar with CSV + Parquet download buttons
- ✅ `useWorkflowData` TanStack Query hook with staleTime caching
- ✅ Tab bar redesign — pill-style tabs with icons (BarChart3, GitBranch, Code2, Shield, Database), count badges
- ✅ Header polish — bolder typography, divider dots, cleaner metadata row
- ✅ SpecsPage Fragment key fix (React warning)
- ✅ Test database isolation — session-scoped autouse fixture sets DATABASE_URL to in-memory SQLite

### Files Created
- `frontend/src/components/DataTab.tsx` (176 lines)
- `IMPLEMENTATION_PLAN_PHASE_13_1.md`, `IMPLEMENTATION_PLAN_PHASE_13_2.md`

### Files Modified
- `src/api/schemas.py`, `src/api/routers/workflows.py`, `src/engine/orchestrator.py`
- `tests/unit/test_api.py`, `tests/conftest.py`
- `frontend/src/types/api.ts`, `frontend/src/lib/api.ts`, `frontend/src/hooks/useWorkflows.ts`
- `frontend/src/pages/WorkflowDetailPage.tsx`, `frontend/src/pages/SpecsPage.tsx`

---

## Phase 14 — YAML-Driven Orchestration Pipeline (F02/F03)

**Implemented:** 2026-04-11
**Agents:** `python-fastapi` (14.1, 14.2, 14.3-backend, 14.4), `vite-react` (14.3-frontend)
**Tooling:** ✅ All pass (243 tests, 20 import contracts)

### Phase 14.1 — Pipeline Models + Step Executors
- ✅ `StepType` StrEnum (agent, builtin, gather, parallel_map, hitl_gate)
- ✅ `StepDefinition` + `PipelineDefinition` frozen Pydantic models with YAML parser
- ✅ `PipelineContext` dataclass for inter-step state passing
- ✅ 5 typed step executors: Agent, Builtin, Gather, ParallelMap, HITLGate
- ✅ `STEP_EXECUTOR_REGISTRY` + `BUILTIN_REGISTRY` + `build_agent_deps_and_prompt` dispatcher
- ✅ 3 new `AuditAction` enum members (STEP_STARTED, STEP_COMPLETED, HITL_GATE_WAITING)

### Phase 14.2 — Pipeline Interpreter + Default YAML
- ✅ `PipelineInterpreter` — topological sort (Kahn's algorithm) + step dispatch loop
- ✅ `config/pipelines/clinical_derivation.yaml` — standard 6-step flow (backward-compatible)
- ✅ `docs/COMPOSITION_LAYER.md` — architecture justification with CrewAI/LangGraph comparison
- ✅ `parse_spec` builtin mirrors orchestrator._step_spec_review

### Phase 14.3 — API Endpoint + Frontend Diagram
- ✅ `GET /api/v1/pipeline` endpoint with `PipelineOut` schema
- ✅ `PipelineView.tsx` — ReactFlow + dagre LR diagram with type-colored nodes
- ✅ 6th "Pipeline" tab on WorkflowDetailPage

### Phase 14.4 — Scenario Pipelines + Tests
- ✅ `express.yaml` — 4 steps (no QC, no audit, no HITL gate)
- ✅ `enterprise.yaml` — 8 steps (3 HITL gates for 21 CFR Part 11)
- ✅ 28 scenario tests (parameterized cross-cutting) + 4 integration tests
- ✅ 5 equivalence tests proving pipeline interpreter matches old orchestrator

### Phase 14.5 — API Wiring + FSM Auto-Generation
- ✅ `PipelineFSM` — lightweight state tracker, states auto-derived from pipeline step IDs
- ✅ `create_pipeline_orchestrator` factory function
- ✅ `WorkflowManager` fully switched to PipelineInterpreter (old orchestrator kept as reference)
- ✅ All API endpoints adapted (status, approve, audit, dag use context+FSM)
- ✅ HITL approval wired: `get_approval_event()` finds pending asyncio.Event

### Files Created
- `src/domain/pipeline_models.py`, `src/engine/pipeline_context.py`
- `src/engine/step_executors.py`, `src/engine/step_builtins.py`
- `src/engine/pipeline_interpreter.py`, `src/engine/pipeline_fsm.py`
- `src/api/routers/pipeline.py`
- `frontend/src/components/PipelineView.tsx`
- `config/pipelines/clinical_derivation.yaml`, `express.yaml`, `enterprise.yaml`
- `config/README.md`, `docs/COMPOSITION_LAYER.md`
- 7 test files (54 new tests)

---

## Phase 16.1 — Long-Term Memory Wiring

**Implemented:** 2026-04-13
**Agent:** `python-fastapi`
**Commits:** `0d35671`, `55000e9`, `82f57fd`
**Tooling:** ✅ All 18 pre-push hooks pass (282 tests, 19 import contracts)

### Goal
`PatternRepository`, `FeedbackRepository`, `QCHistoryRepository` existed
with full CRUD methods but were never instantiated outside tests. This
phase wires them into the pipeline so the coder agent can cache-hit on
prior approved patterns and post-HITL approvals persist to long-term
memory.

### Completed
- ✅ `query_patterns` PydanticAI tool — fetches up to 3 approved patterns
  per variable type from `PatternRepository`, graceful no-repo fallback
- ✅ `save_patterns` builtin — persists approved DAG nodes +
  `QCHistoryRepository` verdicts after `human_review` gate
- ✅ `PipelineContext.pattern_repo` / `qc_history_repo` (TYPE_CHECKING),
  `CoderDeps.pattern_repo` — repositories injected via DI, not
  instantiated inside engine/agents
- ✅ `src/factory.py` constructs both repos at workflow start
- ✅ `save_patterns` step added to `clinical_derivation.yaml` and
  `enterprise.yaml`, deliberately **omitted** from `express.yaml`
  (no HITL = no human-validated patterns worth keeping)
- ✅ `BaseRepository.commit()` helper so engine code can flush via
  `ctx.pattern_repo.commit()` without touching sqlalchemy directly
- ✅ `AgentRegistry.TOOL_MAP` extended with `query_patterns`

### DI refactor (commits 55000e9, 82f57fd)
- Plan initially had engine/agents instantiating repos directly; that
  tripped the `check_repo_direct_instantiation` pre-push hook.
- Plan also kept `ctx.session: AsyncSession | None`; that tripped the
  `check_raw_sql_in_engine` hook because TYPE_CHECKING-block sqlalchemy
  imports are still parsed by the AST walker.
- Fix: inject repos from `src/factory.py` (outside FORBIDDEN_LAYERS),
  store under TYPE_CHECKING annotations only, call `repo.commit()`
  instead of `session.commit()`. Zero runtime sqlalchemy imports in
  `src/engine/`.

### Files Created
- `src/agents/tools/query_patterns.py` (33 lines)
- `tests/unit/test_query_patterns_tool.py`
- `tests/unit/test_save_patterns_builtin.py`
- `tests/integration/test_long_term_memory.py`
- `IMPLEMENTATION_PLAN_PHASE_16_1.md`

### Files Modified
- `src/agents/deps.py` — `CoderDeps.pattern_repo` (TYPE_CHECKING)
- `src/agents/registry.py` — `TOOL_MAP["query_patterns"]`
- `src/agents/tools/__init__.py` — re-export
- `src/engine/pipeline_context.py` — `pattern_repo`, `qc_history_repo` fields
- `src/engine/derivation_runner.py` — threads `pattern_repo` into `CoderDeps`
- `src/engine/step_executors.py` — passes `ctx.pattern_repo` to `run_variable`
- `src/engine/step_builtins.py` — `save_patterns` builtin + registration
- `src/factory.py` — instantiates both repos, sets them on `PipelineContext`
- `src/persistence/base_repo.py` — `commit()` helper
- `config/agents/coder.yaml`, `qc_programmer.yaml` — add `query_patterns` tool
- `config/pipelines/clinical_derivation.yaml`, `enterprise.yaml` — add `save_patterns` step
- `.importlinter` — TYPE_CHECKING-only edges under 3 contract exceptions

### Tests Added
- +23 tests (5 tool + 5 builtin + 2 integration + 11 absorbed regressions)

### End-to-End Verification (production smoke test)
Ran `simple_mock.yaml` twice against the live backend + agentlens proxy
+ `mailbox_simple_mock.py` auto-responder, approved each HITL gate via
the UI, and inspected `cdde.db` directly:

| Table | Before | After | Delta |
|---|---|---|---|
| `patterns[AGE_GROUP]` | 3 | 5 | **+2** |
| `patterns[TREATMENT_DURATION]` | 3 | 5 | **+2** |
| `patterns[IS_ELDERLY]` | 3 | 5 | **+2** |
| `patterns[RISK_SCORE]` | 3 | 5 | **+2** |
| `qc_history.total` | 19 | 27 | **+8** |

Two runs × 4 approved variables = 8 new pattern rows + 8 new qc_history
rows. The new rows carry fresh `approach` strings distinct from older
rows, confirming they were freshly persisted. The `save_patterns` step
was visible in the FSM timeline (`api_fsm=audit ... db_fsm=save_patterns`).

### Verification Checklist
| Item | Status |
|------|--------|
| All files created | ✅ |
| All tests passing (282) | ✅ |
| Tooling clean (pyright, ruff, lint-imports, 18 pre-push hooks) | ✅ |
| `/check` passes | ✅ |
| End-to-end smoke test against real backend | ✅ |
| Zero runtime sqlalchemy imports in `src/engine/` | ✅ |

---

## Phase 16.2 — HITL Backend (Reject + Override + Rich Approval)

**Implemented:** 2026-04-13
**Agent:** `python-fastapi`
**Sub-phases:** 16.2a (infrastructure) + 16.2b (API surface)
**Commits:** `cd284da` (16.2a), `d337cdd` (16.2b)
**Tooling:** ✅ All 18 pre-push hooks pass (292 tests, 19 import contracts)

### Goal
Close the HITL loop by letting humans **reject** workflows, **override**
per-variable code, and provide **rich feedback** alongside approvals —
and persist every human action into `FeedbackRepository` so the
cross-run learning loop feeds back into future runs.

### Design call-out — rejection flow
**Do NOT call `task.cancel()`.** `asyncio.CancelledError` inherits from
`BaseException`, not `Exception`, so `_run_and_cleanup`'s
`except Exception` would miss it and leak the task. Instead:

1. `WorkflowManager.reject_workflow` sets `ctx.rejection_requested = True`
   + `ctx.rejection_reason`, writes a `FeedbackRow`, then releases the
   HITL `asyncio.Event`.
2. `HITLGateStepExecutor` wakes from `event.wait()`, checks the flag,
   raises `WorkflowRejectedError(reason)`.
3. `WorkflowRejectedError` inherits `CDDEError → Exception`, so the
   existing `_run_and_cleanup` catches it naturally and transitions
   the FSM via the existing `fail()` path. Zero new error handling.

### 16.2a — Infrastructure (commit `cd284da`)
- ✅ `src/domain/exceptions.py` — `NotFoundError`, `WorkflowRejectedError`
  (both inherit `CDDEError`, not `BaseException`)
- ✅ `src/domain/enums.py` — `AuditAction.HUMAN_REJECTED`, `HUMAN_OVERRIDE`
- ✅ `src/engine/pipeline_context.py` — `rejection_requested: bool`,
  `rejection_reason: str` (primitive fields, no new imports)
- ✅ `src/engine/step_executors.py::HITLGateStepExecutor` — checks the
  flag after `event.wait()`, raises `WorkflowRejectedError` on reject
  path, records `HUMAN_REJECTED` audit
- ✅ +2 unit tests for the gate executor reject/approval branches

### 16.2b — API Surface (commit `d337cdd`)
- ✅ `src/api/schemas.py` — `VariableDecision`, `ApprovalRequest`,
  `RejectionRequest`, `VariableOverrideRequest` (all frozen,
  `Field(min_length=1)` on required strings)
- ✅ `src/api/workflow_manager.py` + `src/api/workflow_hitl.py` —
  `get_session`, `approve_with_feedback`, `reject_workflow`. The
  approve path writes one `FeedbackRow` per `VariableDecision`; the
  reject path sets the rejection flag, writes a `FeedbackRow`, then
  releases the gate. Both commit in a single transaction.
- ✅ `src/api/services/override_service.py` — `OverrideService` validates
  the variable exists in the DAG, runs `execute_derivation` on the new
  code, applies the result to `derived_df` **only on success**, updates
  `node.approved_code`, records `HUMAN_OVERRIDE` audit, writes feedback,
  commits once. On failure, raises `DerivationError` without mutating
  state so the router returns 400 with the original code preserved.
- ✅ `src/api/routers/hitl.py` — `POST /approve` (backwards-compatible
  with no body), `POST /reject`, `POST /variables/{var}/override`
- ✅ `src/api/routers/workflows.py` — removed old `/approve` (moved to
  `hitl.py` to keep file under the 300-line limit)
- ✅ `src/api/app.py` — registers `hitl_router`
- ✅ 8 new integration tests covering all paths

### Size refactors
`workflow_manager.py` was hitting the AST class-body limit (230 lines).
Extracted `approve_with_feedback_impl` + `reject_workflow_impl` into
a new `src/api/workflow_hitl.py`; `WorkflowManager` delegates. Mirrors
the `workflow_lifecycle.py` extraction pattern from commit `3a8ee62`.
Adding 3 endpoints to `workflows.py` would have pushed it over 300
lines; added a focused `routers/hitl.py` instead.

### Files Created
- `src/api/services/__init__.py` (2 lines)
- `src/api/services/override_service.py` (94 lines)
- `src/api/workflow_hitl.py` (65 lines)
- `src/api/routers/hitl.py` (82 lines)
- `tests/integration/test_hitl_flows.py` (347 lines, 8 tests)
- `IMPLEMENTATION_PLAN_PHASE_16_2_A.md`, `IMPLEMENTATION_PLAN_PHASE_16_2_B.md`

### Files Modified
- `.importlinter` — 2 new `api → feedback_repo` exceptions (landed in
  16.2b because import-linter rejects unmatched `ignore_imports` entries)
- `src/api/schemas.py` — 4 new frozen request schemas
- `src/api/workflow_manager.py` — `get_session` + 2 delegating methods
- `src/api/app.py` — register `hitl_router`
- `src/api/routers/workflows.py` — removed `/approve` (now in `hitl.py`)

### Tests Added
- **16.2a:** 2 unit tests (gate executor reject + approval paths)
- **16.2b:** 8 integration tests
  1. `test_reject_workflow_sets_flag_and_writes_feedback`
  2. `test_reject_with_empty_reason_returns_422`
  3. `test_approve_with_per_variable_payload_writes_feedback`
  4. `test_approve_with_no_body_releases_gate` (backwards compat)
  5. `test_override_variable_rewrites_approved_code`
  6. `test_override_variable_with_invalid_code_returns_400`
  7. `test_override_unknown_variable_returns_404`
  8. `test_reject_on_workflow_not_at_gate_returns_409`

### Verification Checklist
| Item | Status |
|------|--------|
| All files created | ✅ |
| 292 tests passing (+10 new) | ✅ |
| No `task.cancel()` anywhere in the new code (grep verified) | ✅ |
| Rejection path stays inside `Exception` hierarchy | ✅ |
| `workflow_manager.py` class body under AST limit | ✅ |
| `routers/workflows.py` + `routers/hitl.py` both under 300 lines | ✅ |
| Tooling clean (pyright, ruff, lint-imports, 18 pre-push hooks) | ✅ |

---

## Phase 16.3 — HITL Frontend Surface

**Implemented:** 2026-04-13
**Agent:** `vite-react` (all 3 sub-phases)
**Sub-phases:** 16.3.0 (test infra) + 16.3a (plumbing) + 16.3b (dialogs + wiring)
**Commits:** none yet — awaiting `/check` review before commit
**Frontend tooling:** ✅ `pnpm tsc --noEmit`, `pnpm eslint`, `pnpm test`, `pnpm vite build` all green vs pre-existing baseline

### Goal
Surface Phase 16.2b's new backend endpoints (`/reject`, `/approve` with
payload, `/variables/{var}/override`) in the frontend so reviewers can
actually reject, approve per-variable, and edit code from the UI.

### 16.3.0 — Test Infrastructure
Frontend had no test harness at all (no vitest, no testing-library, no
`test` script). This phase installed:
- `vitest@4.1.4`, `@testing-library/react@16.3.2`,
  `@testing-library/user-event@14.6.1`,
  `@testing-library/jest-dom@6.9.1`, `jsdom@29.0.2`, `@vitest/ui@4.1.4`
- `frontend/vitest.config.ts` (jsdom env, globals, `@/* → src/*` alias
  matching `tsconfig.app.json`)
- `frontend/src/test-setup.ts` (imports jest-dom matchers)
- `test`, `test:watch`, `test:ui` scripts in `package.json`
- `tsconfig.node.json` extended to type-check the new `vitest.config.ts`

Zero product code changes. `pnpm test` exits 0 with
`passWithNoTests: true` until 16.3b adds actual tests.

### 16.3a — Plumbing (types, client, hooks, primitive)
- **`frontend/src/components/ui/textarea.tsx`** — shadcn Textarea
  primitive (missing from the repo); forwardRef so React Hook Form
  works; mirrors the existing `ui/input.tsx` style but adapted
  because `input.tsx` wraps `@base-ui/react/input` while no base-ui
  textarea counterpart exists
- **`frontend/src/types/api.ts`** — 4 new interfaces mirroring the
  16.2b Pydantic schemas: `VariableDecision`, `ApprovalRequest`,
  `RejectionRequest`, `VariableOverrideRequest` (written as
  `interface` to match the file's existing style, not `type`)
- **`frontend/src/lib/api.ts`** — 3 new methods added as arrow-function
  properties on the existing `const api = { ... }` object:
  `approveWorkflowWithFeedback`, `rejectWorkflow`, `overrideVariable`.
  All use the existing `fetchJson<T>` helper and `BASE = '/api/v1'`
  constant. Existing `approveWorkflow` (no body) kept for backwards
  compat.
- **`frontend/src/hooks/useWorkflows.ts`** — 3 new TanStack mutation
  hooks (`useApproveWorkflowWithFeedback`, `useRejectWorkflow`,
  `useOverrideVariable`) with inline array query keys
  (`['workflow', id]`, `['workflow', id, 'dag']`, `['workflows']`).
  All `mutationFn` bodies call `api.<method>(...)`, never a bare
  function — matches existing hook style. `void` prefix on
  `invalidateQueries` for the `no-floating-promises` rule.

No dialog components, no page wiring, no tests in this sub-phase.

### 16.3b — Dialogs + Wiring
**Created (4 components + 3 test files):**
- `RejectDialog.tsx` (57 lines) — mandatory reason textarea,
  destructive confirm, whitespace-only rejection check, `isRejecting`
  button state
- `VariableApprovalList.tsx` (40 lines) — stateless per-variable
  checkbox list with `StatusBadge` QC verdict reuse and first-80-char
  code snippet; `max-h-96 overflow-y-auto`
- `ApprovalDialog.tsx` (112 lines) — wraps the list + optional reason
  textarea; initializes `decisions` state as approve-all. **12 lines
  over the 100-line spec target** because the `react-hooks/set-state-in-effect`
  ESLint rule forced extracting an inner `ApprovalDialogBody` keyed
  by the variables prop to reset state on reopen — the idiomatic React
  answer. Still well under the 200-line hard cap.
- `CodeEditorDialog.tsx` (114 lines) — monospace `rows={20}` code
  textarea pre-filled with current code + mandatory reason +
  inline error display from the `error` prop; save disabled when
  code unchanged, reason empty, or saving in progress. Plain
  textarea (no syntax highlighting) — explicit demo-grade choice;
  production would use CodeMirror.
- `RejectDialog.test.tsx` (70 lines, 5 tests), `ApprovalDialog.test.tsx`
  (104 lines, 3 tests), `CodeEditorDialog.test.tsx` (84 lines, 5 tests)
  — pure component tests via props + callbacks, no MSW. RTL queries
  are `getByRole`/`getByLabelText`/`getByText`, no class-name assertions.

**Modified:**
- `WorkflowHeader.tsx` (146/150 lines) — removed the single `onApprove`
  button, added Approve + Reject buttons inside the amber HITL alert,
  mounted `ApprovalDialog` and `RejectDialog`. New props: `dagNodes`,
  `onReject`, `onApproveWithFeedback`, `isRejecting`.
- `CodePanel.tsx` (93 lines) — added an Edit button next to the
  approved-code heading for each variable, visible only when
  `status.awaiting_approval === true`. Mounts `CodeEditorDialog`
  keyed by `editingVariable`, wires `useOverrideVariable(workflowId)`
  with `onSuccess` auto-close.
- `WorkflowTabs.tsx` (118 lines) — **pass-through addition** —
  `CodePanel` is rendered inside `WorkflowTabs`, not directly in
  `WorkflowDetailPage`, so `workflowId` + `status` had to be
  threaded through here (a fact not in the original plan — the
  subagent read the code and adapted correctly).
- `WorkflowDetailPage.tsx` (78 lines) — added
  `useApproveWorkflowWithFeedback`, `useRejectWorkflow`,
  `useWorkflowDag` wiring; passes `dagNodes ?? []` into
  `WorkflowHeader`; removed the old `useApproveWorkflow` import.
- `tsconfig.app.json` — surgical addition of `"vitest/globals"` and
  `"@testing-library/jest-dom"` to `compilerOptions.types` so the
  new test files type-check.

### Tests Added
- **0 tests in 16.3.0** (test harness only)
- **0 tests in 16.3a** (plumbing only)
- **13 tests in 16.3b** (component tests, all passing)

### Verification Checklist
| Item | Status |
|------|--------|
| All 4 dialog components created | ✅ |
| Reject button visible when `awaiting_approval=true` | ✅ |
| Approve opens per-variable dialog with approve-all default | ✅ |
| Edit button per variable, only when awaiting approval | ✅ |
| Override mutation invalidates dag + result query keys | ✅ |
| API errors surface inline in `CodeEditorDialog` | ✅ |
| 13 component tests covering happy/error/edge paths | ✅ |
| All type references use `DAGNode` (never `DAGNodeOut`) | ✅ |
| `pnpm tsc --noEmit` zero new errors vs baseline | ✅ |
| `pnpm eslint` zero new errors vs baseline | ✅ |
| `pnpm vite build` clean | ✅ |
| 13/13 component tests pass | ✅ |

### Plan Adaptations (subagent judgment calls)
1. **`interface` over `type`** in `types/api.ts` — matches existing
   file style.
2. **`forwardRef` for Textarea** despite `input.tsx` using base-ui —
   no base-ui textarea counterpart exists; forwardRef is the right
   React pattern for form library compatibility.
3. **Keyed inner-body component in `ApprovalDialog`** instead of
   `useEffect` + `setState` for prop-driven state reset — the project's
   strict ESLint config bans that pattern via
   `react-hooks/set-state-in-effect`. Added 12 lines over the spec
   target, within the hard limit.
4. **`CodePanel` prop threading via `WorkflowTabs`** — the plan
   assumed `CodePanel` was a direct child of `WorkflowDetailPage`,
   but it's rendered inside `WorkflowTabs` via a map. Subagent read
   the code and threaded `workflowId` + `status` through correctly.
5. **Native `<input type="checkbox">` in `VariableApprovalList`** —
   no shadcn `ui/checkbox.tsx` exists in the project.

---

## Next Phase Preview

**Phases 16.4, 16.5** — per the `IMPLEMENTATION_PLAN_PHASE_16_4.md`
and `IMPLEMENTATION_PLAN_PHASE_16_5.md` plan files (not yet reviewed
in detail). Dependencies: Phase 16.3 ✅ (awaiting commit/push).

---

## All Phases 1-16.3 Complete ✅

**Current metrics:** 292 backend tests + 13 frontend tests | 19 import contracts | 18 pre-push hooks | 10 custom arch checks | 0 gaps

**Awaiting:** `/check` review of the uncommitted 16.3 delta before commit/push (per user instruction).
