# Fix Plan — CDDE

**Date:** 2026-04-10
**Based on:** REVIEW.md dated 2026-04-10
**Project type:** Python/FastAPI + Vite/React

## Summary

| Phase | Fix Units | Files Affected | Estimated Effort |
|-------|-----------|---------------|-----------------|
| Phase 0 — Micro-fixes | 5 | 16 | Low (30 min) |
| Phase 1 — Structural | 4 | 12 | Medium (1-2h) |
| Phase 2 — Architectural | 3 | 8 | High (2-3h) |
| **Total** | **12** | **36** | |

**Agents required:** `python-fastapi`, `vite-react`

---

## Phase 0 — Micro-fixes

### Fix Unit 0.1: Add missing enum members + replace raw strings in orchestrator
- **Category:** State & Enums (Critical)
- **Agent:** `python-fastapi`
- **Files:**
  - `src/domain/models.py` — add enum members
  - `src/engine/orchestrator.py` — replace raw strings
  - `src/engine/orchestrator_helpers.py` — drop .value unwraps
- **HOW TO FIX:**
  1. In `src/domain/models.py`, add to `AuditAction`: `HUMAN_APPROVED = "human_approved"`
  2. In `src/domain/models.py`, add to `AgentName`: `HUMAN = "human"`
  3. In `src/engine/orchestrator.py:80`, replace `== "review"` with `== WorkflowStep.REVIEW.value` (note: `current_state_value` returns a string, so `.value` IS needed here for python-statemachine — but import WorkflowStep)
  4. In `src/engine/orchestrator.py:84`, replace `action="human_approved"` with `action=AuditAction.HUMAN_APPROVED` and `agent="human"` with `agent=AgentName.HUMAN`
  5. In `src/engine/orchestrator_helpers.py:60`, replace `WorkflowStep.COMPLETED.value` with just `WorkflowStep.COMPLETED.value` — KEEP as-is, `current_state_value` returns str not enum so `.value` comparison is actually correct here
  6. In `src/engine/orchestrator.py:153`, replace `or "unknown"` with appropriate handling
- **Verification:** `grep -rn '"human_approved"\|"human"\|== "review"' src/engine/` should return zero raw strings

### Fix Unit 0.2: Add response_model to approve and adam endpoints
- **Category:** Architecture (Critical)
- **Agent:** `python-fastapi`
- **Files:**
  - `src/api/routers/workflows.py`
- **HOW TO FIX:**
  1. Line 58: change `@router.post("/{workflow_id}/approve", status_code=200)` to `@router.post("/{workflow_id}/approve", response_model=WorkflowStatusResponse, status_code=200)`
  2. Line 166: change `@router.get("/{workflow_id}/adam", status_code=200)` to `@router.get("/{workflow_id}/adam", response_class=FileResponse, status_code=200)`
- **Verification:** `grep '@router\.' src/api/routers/workflows.py` — every decorator should have response_model or response_class

### Fix Unit 0.3: Add `from __future__ import annotations` to __init__.py files
- **Category:** Typing (Medium)
- **Agent:** `python-fastapi`
- **Files:**
  - `src/persistence/__init__.py`
  - `src/agents/tools/__init__.py`
  - `src/ui/__init__.py`
  - `src/ui/components/__init__.py`
  - `src/ui/pages/__init__.py`
- **HOW TO FIX:** Add `from __future__ import annotations` as the first line (after any module docstring) in each file
- **Verification:** `grep -L "from __future__" src/**/__init__.py` should return only empty __init__.py files

### Fix Unit 0.4: Add Any justification comments
- **Category:** Typing (Medium)
- **Agent:** `python-fastapi`
- **Files:**
  - `src/domain/synthetic.py:7`
  - `src/domain/executor.py:9`
  - `src/verification/comparator.py:11`
  - `src/persistence/base_repo.py:5`
  - `src/domain/spec_parser.py:6`
- **HOW TO FIX:** Add inline comment after each `Any` import explaining why:
  - `synthetic.py`: `# Any: pandas Series dtype param not narrowable`
  - `executor.py`: `# Any: pd.Series[Any] — pandas stubs use Any for series dtype`
  - `comparator.py`: `# Any: pd.Series[Any] — pandas stubs don't narrow from read_json`
  - `base_repo.py`: already has comment — verify it exists
  - `spec_parser.py`: `# Any: YAML safe_load returns untyped dict`
- **Verification:** `grep "from typing import.*Any" src/ -rn | grep -v "#"` should return zero uncommented Any imports

### Fix Unit 0.5: Consolidate TERMINAL_STATES in frontend
- **Category:** State & Enums (Medium)
- **Agent:** `vite-react`
- **Files:**
  - `frontend/src/lib/status.ts` — add export
  - `frontend/src/hooks/useWorkflows.ts` — import instead of defining locally
  - `frontend/src/pages/WorkflowDetailPage.tsx` — import instead of defining locally
  - `frontend/src/pages/DashboardPage.tsx` — import instead of inline arrays
- **HOW TO FIX:**
  1. In `frontend/src/lib/status.ts`, add: `export const TERMINAL_STATUSES = ['completed', 'failed'] as const`
  2. In `useWorkflows.ts`, remove line 4 (`const TERMINAL_STATES = ...`), add `import { TERMINAL_STATUSES } from '@/lib/status'`, replace all refs
  3. In `WorkflowDetailPage.tsx`, remove line 13 (`const TERMINAL = ...`), add `import { TERMINAL_STATUSES } from '@/lib/status'`, replace
  4. In `DashboardPage.tsx`, replace inline `['completed', 'failed']` on lines 21-22 with `TERMINAL_STATUSES`
  5. Also add missing WorkflowStep values to STATUS_COLOR_MAP: `created: 'blue'`, `spec_review: 'blue'`, `dag_built: 'blue'`, `deriving: 'amber'`, `debugging: 'amber'`
  6. Remove phantom entries: `initialized`, `started` (backend never emits these)
- **Verification:** `grep "'completed', 'failed'" frontend/src/` should only match `status.ts`

---

## Phase 1 — Structural

### Fix Unit 1.1: Route WorkflowManager DB queries through repository
- **Category:** Architecture (Critical)
- **Agent:** `python-fastapi`
- **Files:**
  - `src/persistence/workflow_state_repo.py` — add `list_all()` method
  - `src/api/workflow_manager.py` — replace raw queries with repo calls
  - `src/api/app.py` — inject repo into WorkflowManager via lifespan
- **HOW TO FIX:**
  1. In `workflow_state_repo.py`, add method:
     ```python
     async def list_all(self) -> list[tuple[str, str, str]]:
         """Return all (workflow_id, fsm_state, state_json) tuples."""
         result = await self._execute(select(WorkflowStateRow))
         return [(r.workflow_id, r.fsm_state, r.state_json) for r in result.scalars()]
     ```
  2. In `workflow_manager.py`, replace `load_history()` to accept a `WorkflowStateRepository` param instead of creating its own session
  3. In `workflow_manager.py`, replace `delete_workflow()` to accept a repo or use an injected one
  4. In `app.py` lifespan, create a session + repo and pass to `manager.load_history(repo)`
  5. Remove all `from sqlalchemy import` and `from src.persistence.orm_models import` from workflow_manager.py
- **Verification:** `grep "sqlalchemy\|orm_models" src/api/workflow_manager.py` should return zero matches

### Fix Unit 1.2: Change CORS default from wildcard
- **Category:** Security (Medium)
- **Agent:** `python-fastapi`
- **Files:**
  - `src/config/settings.py`
- **HOW TO FIX:**
  1. Change `cors_origins: str = "*"` to `cors_origins: str = "http://localhost:3000"`
  2. Update `.env.example` with comment: `# CORS_ORIGINS=https://your-domain.com  # comma-separated for production`
- **Verification:** `grep 'cors_origins.*"\\*"' src/config/settings.py` should return zero

### Fix Unit 1.3: Add tests for untested API endpoints and WorkflowManager methods
- **Category:** Testing (Critical + High)
- **Agent:** `python-fastapi`
- **Files:**
  - `tests/unit/test_api.py` — add approve, delete, list tests
  - `tests/unit/test_workflow_manager.py` — add load_history, delete, is_known tests
- **HOW TO FIX:**
  1. In `test_api.py`, add:
     - `test_list_workflows_returns_array` — GET /api/v1/workflows/ → 200, returns list
     - `test_approve_nonexistent_returns_404` — POST /approve on unknown ID → 404
     - `test_delete_workflow_returns_204` — DELETE on existing workflow → 204
  2. In `test_workflow_manager.py`, add:
     - `test_is_known_after_start_returns_true`
     - `test_get_historic_unknown_returns_none` (already exists — verify)
     - `test_delete_workflow_removes_from_known`
- **Verification:** `uv run pytest tests/unit/test_api.py tests/unit/test_workflow_manager.py -v` — all pass

### Fix Unit 1.4: Add match= to bare pytest.raises
- **Category:** Testing (Medium)
- **Agent:** `python-fastapi`
- **Files:**
  - `tests/unit/test_agent_factory.py:64` — add `match="output_type"` or similar
  - `tests/unit/test_spec_parser.py:32,67` — add match patterns
  - `tests/integration/test_workflow.py:100` — add match pattern
- **HOW TO FIX:** Read each test, determine what the expected error message contains, add `match="..."` kwarg
- **Verification:** `grep "pytest.raises(" tests/ -rn | grep -v "match="` should return zero (excluding comment lines)

---

## Phase 2 — Architectural

### Fix Unit 2.1: Create test_orchestrator_helpers.py
- **Category:** Testing (Critical)
- **Agent:** `python-fastapi`
- **Files:**
  - `tests/unit/test_orchestrator_helpers.py` — NEW
- **HOW TO FIX:** Create tests for:
  - `test_serialize_workflow_state_with_dag_includes_nodes`
  - `test_serialize_workflow_state_without_dag_returns_empty_nodes`
  - `test_build_workflow_result_completed_status`
  - `test_build_workflow_result_failed_status`
  - `test_build_derivation_details_match_resolution`
  - `test_build_derivation_details_mismatch_debugger_resolution`
- **Reference:** Follow AAA pattern from `tests/unit/test_dag.py`

### Fix Unit 2.2: Narrow AuditRecord and AuditTrail to use enums
- **Category:** State & Enums (Critical)
- **Agent:** `python-fastapi`
- **Dependencies:** Fix Unit 0.1 must be done first (adds enum members)
- **Files:**
  - `src/domain/models.py` — change AuditRecord.action to `AuditAction | str`, .agent to `AgentName | str`
  - `src/audit/trail.py` — narrow `record()` params to accept enum types
  - `src/engine/orchestrator.py` — verify all callers use enum members
  - `src/domain/workflow_fsm.py` — verify uses enum members
- **HOW TO FIX:**
  1. In `models.py`, change `AuditRecord`: `action: AuditAction | str` and `agent: AgentName | str` (gradual — keeps backward compat with FSM string concatenation `f"{AuditAction.STATE_TRANSITION}:{target.id}"`)
  2. In `trail.py`, update `record()` signature: `action: AuditAction | str`, `agent: AgentName | str`
  3. Verify all callers in orchestrator.py and workflow_fsm.py use enum members
- **Note:** Full narrowing to pure enum (removing `| str`) blocked by FSM's `f"{AuditAction.STATE_TRANSITION}:{target.id}"` pattern which concatenates enum + string. This is a known compromise.

### Fix Unit 2.3: Extract OrchestratorConfig to reduce __init__ params
- **Category:** Typing (Critical)
- **Agent:** `python-fastapi`
- **Files:**
  - `src/engine/orchestrator.py` — add dataclass, update __init__
  - `src/factory.py` — update to use config
  - `tests/unit/test_orchestrator.py` — update fixture
- **HOW TO FIX:**
  1. Create in orchestrator.py (or a new file):
     ```python
     @dataclass
     class OrchestratorRepos:
         pattern_repo: PatternRepository | None = None
         qc_repo: QCHistoryRepository | None = None
         state_repo: WorkflowStateRepository | None = None
     ```
  2. Update `__init__` to accept `repos: OrchestratorRepos | None = None` instead of 3 separate params
  3. Update `factory.py` to build `OrchestratorRepos` and pass it
  4. Update test fixtures
- **Verification:** `DerivationOrchestrator.__init__` should have ≤5 params

---

## Deferred Items (not planned)

| Item | Reason |
|------|--------|
| Frontend test suite (Vitest + RTL) | Large scope — separate initiative, not blocking homework submission |
| Test Orchestrator.run() with TestModel | Requires LLM mock infrastructure — important but complex |
| Alembic migration setup | Production concern — homework uses create_all() |
| Split Settings into per-concern classes | Low impact for homework scope |
| Add pagination to GET /workflows/ | Low priority — small dataset |
| Collapse WorkflowStatus into WorkflowStep | Risk of breaking changes across layers |
| Frontend ApiError typed class | Nice-to-have, not blocking |
| Move YAML spec content to TanStack Query | Minor UX improvement |

## Execution Notes

- Run `/fix-review` to execute this plan. It will read this file and follow fix units in order.
- Phase 0 units are independent — can run in parallel.
- Phase 1 units: 1.1 is independent, 1.3 and 1.4 are independent.
- Phase 2 units: 2.2 depends on 0.1. Others are independent.
- For mixed projects: units tagged `python-fastapi` run with that agent, `vite-react` for frontend.
