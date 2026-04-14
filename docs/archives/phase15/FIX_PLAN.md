# Fix Plan — CDDE

**Date:** 2026-04-11
**Based on:** REVIEW.md dated 2026-04-11 (post-Phase 14)
**Project type:** Python/FastAPI + Vite/React

## Summary

| Phase | Fix Units | Files Affected | Estimated Effort |
|-------|-----------|---------------|-----------------|
| Phase 0 — Micro-fixes | 5 | 18 | Low (30 min) |
| Phase 1 — Structural | 5 | 15 | Medium (2-3h) |
| Phase 2 — Architectural | 3 | 10 | High (2-3h) |
| **Total** | **13** | **43** | |

**Agents required:** `python-fastapi`, `vite-react`

---

## Phase 0 — Micro-fixes

### Fix Unit 0.1: Add `frozen=True` to WorkflowCreateRequest + CORS + future annotations
- **Category:** Architecture + Typing (Critical + Medium)
- **Agent:** `python-fastapi`
- **Files:**
  - `src/api/schemas.py` — add `frozen=True` to `WorkflowCreateRequest`
  - `src/api/app.py` — restrict CORS methods/headers
  - `src/__init__.py`, `src/agents/__init__.py`, `src/api/__init__.py`, `src/api/routers/__init__.py`, `src/audit/__init__.py`, `src/config/__init__.py`, `src/domain/__init__.py`, `src/engine/__init__.py`, `src/verification/__init__.py` — add `from __future__ import annotations`
- **HOW TO FIX:**
  1. In `schemas.py:8`, change `class WorkflowCreateRequest(BaseModel):` to `class WorkflowCreateRequest(BaseModel, frozen=True):`
  2. In `app.py:57-58`, change `allow_methods=["*"]` to `allow_methods=["GET", "POST", "DELETE"]` and `allow_headers=["*"]` to `allow_headers=["Content-Type"]`
  3. In each `__init__.py`, add `from __future__ import annotations` as the first line (after any module docstring)
- **Verification:** `grep -L "from __future__" src/**/__init__.py` returns empty

### Fix Unit 0.2: Add `match=` to bare pytest.raises
- **Category:** Testing (Critical)
- **Agent:** `python-fastapi`
- **Files:**
  - `tests/unit/test_models.py:30,126`
  - `tests/unit/test_workflow_fsm.py:45,98,107`
  - `tests/unit/test_spec_parser.py:42`
- **HOW TO FIX:** Read each test, determine what the expected error message contains, add `match="..."` kwarg. For `ValidationError` tests, match on the field name (e.g., `match="variable"` or `match="frozen"`). For `TransitionNotAllowed`, match on the transition name. For `yaml.YAMLError`, match on a YAML error keyword.
- **Verification:** `grep "pytest.raises(" tests/ -rn | grep -v "match="` returns zero

### Fix Unit 0.3: Add import-linter contract + update stale comments
- **Category:** Architecture (Critical)
- **Agent:** `python-fastapi`
- **Files:**
  - `.importlinter`
- **HOW TO FIX:**
  1. Remove or update the stale comment block at lines 11-13 (the "commented out" note about Phase 4 contracts that are now active)
  2. Add a new contract after `api-no-ui`:
     ```ini
     [importlinter:contract:api-no-persistence]
     name = API cannot import from Persistence directly
     type = forbidden
     source_modules = src.api
     forbidden_modules = src.persistence
     ignore_imports =
         src.api.routers.workflows -> src.persistence.database
         src.api.routers.workflows -> src.persistence.workflow_state_repo
     ```
     Note: The `ignore_imports` are temporary — Fix Unit 1.3 will remove these direct imports. After 1.3, remove the ignore_imports lines.
- **Verification:** `uv run lint-imports` passes with the new contract

### Fix Unit 0.4: Add COMPOSITION_LAYER.md cross-reference to ARCHITECTURE.md
- **Category:** Documentation (Medium)
- **Agent:** `python-fastapi`
- **Files:**
  - `ARCHITECTURE.md`
- **HOW TO FIX:** In the `## YAML-Driven Pipeline Engine` section, add after the last paragraph:
  ```
  See [docs/COMPOSITION_LAYER.md](docs/COMPOSITION_LAYER.md) for the full justification of building this composition layer on top of PydanticAI, including comparisons with CrewAI, LangGraph, Prefect, and Temporal.
  ```
- **Verification:** `grep "COMPOSITION_LAYER" ARCHITECTURE.md` returns a match

### Fix Unit 0.5: Replace raw string status literals in PipelineFSM
- **Category:** State & Enums (Critical)
- **Agent:** `python-fastapi`
- **Files:**
  - `src/engine/pipeline_fsm.py`
- **HOW TO FIX:**
  1. Add import: `from src.domain.models import WorkflowStep`
  2. Replace `self._current: str = "created"` with `self._current: str = WorkflowStep.CREATED.value`
  3. Replace `self._current = "completed"` with `self._current = WorkflowStep.COMPLETED.value`
  4. Replace `self._current = "failed"` with `self._current = WorkflowStep.FAILED.value`
  5. Replace `return self._current in ("completed", "failed")` with `return self._current in (WorkflowStep.COMPLETED.value, WorkflowStep.FAILED.value)`
  6. Note: `.value` IS needed because `_current` is a `str` and `current_state_value` returns a `str` — the comparison must be string-to-string
- **Verification:** `grep '"completed"\|"failed"\|"created"' src/engine/pipeline_fsm.py` returns zero

---

## Phase 1 — Structural

### Fix Unit 1.1: Split `models.py` enums into `enums.py`
- **Category:** File size (Critical)
- **Agent:** `python-fastapi`
- **Files:**
  - `src/domain/models.py` — move all StrEnum classes out
  - `src/domain/enums.py` — NEW file with all StrEnum classes
- **HOW TO FIX:**
  1. Create `src/domain/enums.py` with all StrEnum classes from `models.py`: `OutputDType`, `DerivationStatus`, `QCVerdict`, `CorrectImplementation`, `ConfidenceLevel`, `AuditAction`, `AgentName`, `WorkflowStep`
  2. In `models.py`, replace the enum definitions with imports from `enums.py`
  3. Keep `models.py` re-exporting the enums for backward compatibility: `from src.domain.enums import OutputDType, DerivationStatus, ...` (so existing imports don't break)
  4. Both files should be under 150 lines
- **Verification:** `wc -l src/domain/models.py src/domain/enums.py` — both under 150

### Fix Unit 1.2: Delete dead old orchestrator code
- **Category:** Dead code / YAGNI (Critical)
- **Agent:** `python-fastapi`
- **Dependencies:** Verify no test failures after deletion
- **Files:**
  - `src/engine/orchestrator.py` — DELETE
  - `src/domain/workflow_fsm.py` — DELETE
  - `src/engine/orchestrator_helpers.py` — DELETE
  - `src/factory.py` — remove `create_orchestrator()` and its imports
  - `src/api/workflow_manager.py` — remove `get_orchestrator()` shim + TYPE_CHECKING import
  - `tests/unit/test_orchestrator.py` — DELETE
  - `tests/unit/test_orchestrator_helpers.py` — DELETE
  - `tests/unit/test_workflow_fsm.py` — DELETE
- **HOW TO FIX:**
  1. Delete the 3 source files
  2. Delete the 3 test files
  3. In `factory.py`, remove `from src.engine.orchestrator import DerivationOrchestrator, OrchestratorRepos` and the `create_orchestrator()` function. Keep only `create_pipeline_orchestrator()`
  4. In `workflow_manager.py`, remove the `TYPE_CHECKING` import of `DerivationOrchestrator` and the `get_orchestrator()` method
  5. In `.importlinter`, remove the `ignore_imports = src.engine.orchestrator -> src.persistence` line from the `engine-no-persistence` contract
  6. Run `uv run pytest` — if `tests/integration/test_workflow.py` imports the old orchestrator, update it to use the pipeline path or delete it
- **Verification:** `grep -rn "DerivationOrchestrator\|WorkflowFSM\|orchestrator_helpers" src/ tests/` returns zero

### Fix Unit 1.3: Push delete_workflow DB session into WorkflowManager
- **Category:** Architecture (Critical)
- **Agent:** `python-fastapi`
- **Files:**
  - `src/api/routers/workflows.py` — simplify delete endpoint
  - `src/api/workflow_manager.py` — add DB session handling to delete_workflow
- **HOW TO FIX:**
  1. In `WorkflowManager.delete_workflow()`, change signature to not require an external `state_repo` param. Instead, have the manager create its own session internally (similar to how `_run_and_cleanup` does).
  2. In the router's `delete_workflow()`, remove all `init_db()` / `session` / `WorkflowStateRepository` code. Just call `await manager.delete_workflow(workflow_id)`.
  3. After this fix, remove the `ignore_imports` lines from the `api-no-persistence` contract added in Fix Unit 0.3
- **Verification:** `grep "init_db\|WorkflowStateRepository\|session" src/api/routers/workflows.py` returns zero

### Fix Unit 1.4: Replace raw string status literals in router + manager
- **Category:** State & Enums (Critical)
- **Agent:** `python-fastapi`
- **Dependencies:** Fix Unit 1.1 (enums available from `enums.py`)
- **Files:**
  - `src/api/routers/workflows.py`
  - `src/api/workflow_manager.py`
  - `src/api/mcp_server.py`
- **HOW TO FIX:**
  1. In `workflows.py:49`, replace `status="running"` with `status=WorkflowStep.DERIVING.value` (or add `RUNNING = "running"` to `WorkflowStep` if "running" is a distinct concept)
  2. In `workflows.py:260`, replace `status="unknown"` with a proper error — either raise `HTTPException(404)` or add `UNKNOWN = "unknown"` to `WorkflowStep`
  3. In `workflows.py:136,139,200`, replace `"unknown"` fallback strings with `WorkflowStep.CREATED.value` or a documented default
  4. In `workflow_manager.py:122`, replace raw `"failed"` with `fsm.current_state_value` (fsm.fail() was already called)
  5. In `workflow_manager.py:171`, replace `"unknown"` with a WorkflowStep member
  6. In `mcp_server.py:52`, replace `"unknown"` with a WorkflowStep member
- **Verification:** `uv run python tools/pre_commit_checks/check_enum_discipline.py` passes

### Fix Unit 1.5: Create missing test files
- **Category:** Testing (Critical)
- **Agent:** `python-fastapi`
- **Files:**
  - `tests/unit/test_step_builtins.py` — NEW
  - `tests/unit/test_pipeline_context.py` — NEW
  - `tests/unit/test_pipeline_fsm.py` — ADD invalid-transition tests
- **HOW TO FIX:**
  1. Create `test_step_builtins.py` with tests for each builtin function:
     - `test_builtin_parse_spec_populates_context` (happy path with sample_spec_path)
     - `test_builtin_parse_spec_missing_init_raises` (no _init.spec_path)
     - `test_builtin_build_dag_populates_context` (happy path)
     - `test_builtin_build_dag_missing_spec_raises`
     - `test_builtin_export_adam_creates_csv` (happy path with tmp_path)
  2. Create `test_pipeline_context.py` with tests:
     - `test_set_output_and_get_output_roundtrip`
     - `test_get_output_missing_step_raises_key_error`
     - `test_get_output_missing_key_raises_key_error`
  3. Add to `test_pipeline_fsm.py`:
     - `test_fsm_advance_after_complete_still_updates` (documents current behavior — no guard)
     - `test_fsm_fail_is_idempotent` (calling fail twice doesn't crash)
- **Verification:** `uv run pytest tests/unit/test_step_builtins.py tests/unit/test_pipeline_context.py tests/unit/test_pipeline_fsm.py -v` all pass

---

## Phase 2 — Architectural

### Fix Unit 2.1: Split `derivation_runner.py` — extract debug logic
- **Category:** File size (Critical)
- **Agent:** `python-fastapi`
- **Files:**
  - `src/engine/derivation_runner.py` — remove debug logic
  - `src/engine/debug_runner.py` — NEW file with debug functions
- **HOW TO FIX:**
  1. Create `src/engine/debug_runner.py` with: `DebugContext` dataclass, `_debug_variable()`, `_apply_debug_fix()`, `_resolve_approved_code()`
  2. In `derivation_runner.py`, import from `debug_runner` and remove the moved functions
  3. Both files should be under 200 lines
- **Verification:** `wc -l src/engine/derivation_runner.py src/engine/debug_runner.py` — both under 200

### Fix Unit 2.2: Extract WorkflowManager serializer
- **Category:** Class/file size (Critical)
- **Agent:** `python-fastapi`
- **Files:**
  - `src/api/workflow_manager.py` — remove serialization logic
  - `src/api/workflow_serializer.py` — NEW file
- **HOW TO FIX:**
  1. Create `src/api/workflow_serializer.py` with `_serialize_ctx()`, `_build_result()`, and any related helper functions currently in WorkflowManager
  2. In `workflow_manager.py`, import from serializer and remove the moved methods
  3. `WorkflowManager` class should be under 150 lines, file under 200
- **Verification:** `wc -l src/api/workflow_manager.py src/api/workflow_serializer.py` — both under 200

### Fix Unit 2.3: Extract WorkflowDetailPage sub-components
- **Category:** File size (Critical)
- **Agent:** `vite-react`
- **Files:**
  - `frontend/src/pages/WorkflowDetailPage.tsx` — slim down
  - `frontend/src/components/WorkflowHeader.tsx` — NEW
  - `frontend/src/components/WorkflowTabs.tsx` — NEW
- **HOW TO FIX:**
  1. Extract the header section (breadcrumb + title + metadata + error alert + approval banner) into `WorkflowHeader.tsx`
  2. Extract the `<Tabs>` block with all 6 TabsContent sections into `WorkflowTabs.tsx`
  3. `WorkflowDetailPage.tsx` becomes a thin orchestrator: hooks + WorkflowHeader + WorkflowTabs
  4. Target: page under 80 lines, each sub-component under 100 lines
- **Verification:** `wc -l frontend/src/pages/WorkflowDetailPage.tsx` under 100

---

## Deferred Items (not planned)

| Item | Reason |
|------|--------|
| Frontend test suite (Vitest + RTL) | Large scope — separate initiative |
| Type API schema status fields as StrEnum | Requires coordinated backend+frontend change across all consumers |
| Frontend typed `as const` status unions | Depends on schema typing |
| Split `useWorkflows.ts` into domain hooks | Low urgency — functional as-is |
| Move SpecsPage YAML to TanStack Query | Minor UX improvement |
| Extract DataTab → DatasetPanel | At boundary (200 lines), not over |
| Extract `workflows.py` helpers to presenter | Addressed partially by Fix Unit 1.3 |
| Add Vitest CI gate | Requires frontend tests first |
| Alembic migration setup | Production concern, not homework scope |
| Introduce DerivationRunContext dataclass | Tied to derivation_runner split (2.1) |

## Execution Notes

- Run `/fix-review` to execute this plan. It will read this file and follow fix units in order.
- Phase 0 units are independent — can run in parallel.
- Phase 1: 1.1 is independent. 1.2 depends on no other unit. 1.3 depends on 0.3. 1.4 depends on 1.1. 1.5 is independent.
- Phase 2: 2.1 and 2.2 are independent. 2.3 is independent (frontend agent).
- For mixed projects: units tagged `python-fastapi` run with that agent, `vite-react` for frontend.
