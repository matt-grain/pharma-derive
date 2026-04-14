# Review Validation Report — CDDE

**Date:** 2026-04-12
**Review date:** 2026-04-11
**Fix log:** REVIEW_FIX_LOG.md
**Project type:** Python/FastAPI + Vite/React (mixed)
**Validated by:** `/validate-review` — 5 parallel Explore agents + tooling gate
**Healed:** 2026-04-12 — all 7 gaps closed (3 FAILs + 4 PARTIALs)

## Validation Summary

| Category | Findings Checked | ✅ Pass | ⚠️ Partial | ❌ Fail | ⏭️ Deferred | Completion* |
|----------|-----------------|---------|------------|---------|-------------|------------|
| Architecture & SoC | 11 | 6 | 2 | 0 | 3 | 75% |
| Typing & Style | 13 | 9 | 0 | 2 | 2 | 82% |
| State & Enums | 11 | 5 | 0 | 0 | 6 | 100% |
| Testing | 11 | 5 | 0 | 1 | 5 | 83% |
| Documentation & Debt | 11 | 9 | 2 | 0 | 3 | 82% |
| Tooling Checks | 5 | 5 | 0 | 0 | 0 | 100% |
| **TOTAL** | **62** | **39** | **4** | **3** | **19** | **85%** |

*Completion % = Pass / (Pass + Partial + Fail). Deferred items are excluded from the denominator.

## Overall Verdict

✅ **ALL CLEAR (post-heal, 2026-04-12)** — All 7 gaps closed in a single targeted pass. 237 tests passing (up from 234 — 3 new factory tests), 0 pyright errors, 0 ruff errors, 21 import contracts kept, enum discipline clean. `models.py` dropped from 201L → 174L by removing the unused `__all__` block. `workflow_manager.py:40` intentional swallow now has inline justification. `.importlinter` stale Phase 4 note removed + `api-no-persistence` rationale block expanded. Dead-orchestrator docstring mentions intentionally kept as load-bearing historical context.

Completion: **100% of actionable findings** (0 FAIL, 0 PARTIAL, 43 PASS, 19 DEFERRED).

Original validation summary below preserved for audit trail.

## Detailed Results

### 1. Architecture & Separation of Concerns

| Status | Original Finding | Files Checked | Files Still Affected | Details |
|--------|-----------------|---------------|----------------------|---------|
| ✅ PASS | `delete_workflow` router creates DB session / commits | `workflows.py`, `workflow_manager.py` | None | Router one-liner; manager owns session lifecycle |
| ✅ PASS | `WorkflowCreateRequest` not `frozen=True` | `schemas.py` | None | All 12 schemas use `frozen=True` |
| ✅ PASS | Dead orchestrator code still imported | src/, tests/ | None | `orchestrator.py`, `workflow_fsm.py`, `orchestrator_helpers.py` all deleted; 1 docstring mention in `test_pipeline_equivalence.py` acceptable |
| ✅ PASS | CORS wildcard | `app.py` | None | Pinned to `GET, POST, DELETE` + `Content-Type` |
| ✅ PASS | `WorkflowDetailPage.tsx` over 200 lines | page + new components | None | 211→65L; `WorkflowHeader.tsx` (102L) + `WorkflowTabs.tsx` (111L) created |
| ✅ PASS | `.importlinter` missing `api-no-persistence` contract | `.importlinter` | None | Contract exists; `lint-imports` 21 kept, 0 broken |
| ⚠️ PARTIAL | `.importlinter` stale Phase 4 comment | `.importlinter:91` | `.importlinter` | Stale note ("contract will be added in Phase 4") not removed after Phase 4 shipped |
| ⚠️ PARTIAL | `api-no-persistence` ignore_imports exceptions | `.importlinter` | `.importlinter` | Contract still whitelists `src.api.app` + `src.api.workflow_manager` → persistence. Legitimate (manager owns persistence) but not documented as such in the contract |
| ⏭️ DEFERRED | `list_workflows` / `get_workflow_audit` unbounded — no pagination | `workflows.py` | — | Per FIX_PLAN.md |
| ⏭️ DEFERRED | `step_builtins.py` string dispatch (open/closed) | `step_builtins.py` | — | Per FIX_PLAN.md |
| ⏭️ DEFERRED | `useWorkflows.ts` monolithic (11 hooks in one file) | `useWorkflows.ts` | — | Per FIX_PLAN.md |
| ⏭️ DEFERRED | `specs.py` inline YAML parsing | `specs.py` | — | Per FIX_PLAN.md (presenter extraction) |

### 2. Typing & Style

| Status | Original Finding | Files Checked | Files Still Affected | Details |
|--------|-----------------|---------------|----------------------|---------|
| ❌ FAIL | `except Exception` swallowed silently | `workflow_manager.py:40` | `workflow_manager.py` | Line 40 catches, logs via `logger.exception`, rolls back, but **does not re-raise and has no justification comment**. The review rule requires either re-raise OR `# noqa` with rationale |
| ✅ PASS | `except Exception` in old orchestrator | — | — | File deleted |
| ✅ PASS | `except Exception` in Streamlit UI | `ui/pages/workflow.py` | — | Line 46 is UI boundary (displays `st.error`); line 71 rolls back + re-raises |
| ✅ PASS | `WorkflowManager` class 211 lines | `workflow_manager.py` | — | Class is 145 lines (under 150 hard limit) |
| ✅ PASS | `DerivationOrchestrator` 230 lines | — | — | File deleted |
| ❌ FAIL | `models.py` 254 lines target <150 | `models.py` | `models.py` | 254→201L — **1 line over the 200-line hard limit**. `__all__` boilerplate accounts for ~28 lines. Further split needs design decision on Pydantic model grouping |
| ✅ PASS | `derivation_runner.py` 287 lines | files | — | 287→135L; `debug_runner.py` 192L created |
| ✅ PASS | `orchestrator.py` 282 lines | — | — | Deleted |
| ✅ PASS | `workflow_manager.py` 251 lines | `workflow_manager.py` | — | 258→189L; `workflow_serializer.py` 77L created |
| ✅ PASS | 9 `__init__.py` files missing `from __future__` | all 14 `src/**/__init__.py` | — | All present |
| ✅ PASS | All functions have type annotations | `src/**/*.py` | — | pyright strict passes 0/0 |
| ⏭️ DEFERRED | 8 functions with 6+ params in `derivation_runner.py` | `derivation_runner.py` | — | Per FIX_PLAN.md (DerivationRunContext dataclass deferred); derivation_runner now has only 4 functions after split |
| ⏭️ DEFERRED | `verify_derivation` / `_compare_outputs` 7 params each | `comparator.py` | `comparator.py:43,81` | Per FIX_PLAN.md |
| ⏭️ DEFERRED | `workflows.py` 260 lines | `workflows.py` | `workflows.py` (255L) | Per FIX_PLAN.md (presenter extraction) |

### 3. State Management & Enums

| Status | Original Finding | Files Checked | Files Still Affected | Details |
|--------|-----------------|---------------|----------------------|---------|
| ✅ PASS | `PipelineFSM` raw string literals | `pipeline_fsm.py` | None | All assignments use `WorkflowStep.*.value` |
| ✅ PASS | `workflow_manager.py` raw `"failed"` | `workflow_manager.py` | None | Uses `WorkflowStep.FAILED.value` |
| ✅ PASS | Router `status="running"` / `"unknown"` | `workflows.py` | None | Uses `WorkflowStep.RUNNING.value` / `UNKNOWN.value`; new enum members added |
| ✅ PASS | Cross-codebase grep sanity | `src/**/*.py`, `tests/**/*.py` | None | Remaining `"unknown"` literals in router lines 131/134/195 are dict `.get()` fallbacks for `qc_verdict` and `study`, not status positions |
| ✅ PASS | `check_enum_discipline.py` | 53 files | None | Tool passes with zero violations |
| ⏭️ DEFERRED | API schemas `status: str` (5 fields) | `schemas.py` | `schemas.py` | Coordinated backend+frontend change deferred per FIX_PLAN.md |
| ⏭️ DEFERRED | Frontend `types/api.ts` bare `string` | `types/api.ts` | — | Deferred with above |
| ⏭️ DEFERRED | `SpecsPage.tsx` `useState` | `SpecsPage.tsx` | — | Per FIX_PLAN.md |
| ⏭️ DEFERRED | `PipelineStepOut.type` bare `str` | `schemas.py` | — | Per FIX_PLAN.md |
| ⏭️ DEFERRED | `AuditRecordOut.action/agent` bare `str` | `schemas.py` | — | Known compromise per FIX_PLAN.md |
| ⏭️ DEFERRED | `STATUS_COLOR_MAP` gray fallback | `lib/status.ts` | — | Per FIX_PLAN.md |

### 4. Testing Quality

| Status | Original Finding | Files Checked | Files Still Affected | Details |
|--------|-----------------|---------------|----------------------|---------|
| ✅ PASS | `PipelineFSM` zero invalid-transition tests | `test_pipeline_fsm.py` | None | 4 new tests: `after_complete_is_noop`, `fail_is_idempotent`, `advance_after_fail_overwrites`, `complete_after_fail_sets_completed` |
| ✅ PASS | 2 bare `pytest.raises` without `match=` | `tests/**/*.py` | None | Zero bare calls remaining |
| ✅ PASS | `step_builtins.py` no dedicated test file | `test_step_builtins.py` | None | 17 tests, AAA pattern |
| ✅ PASS | `pipeline_context.py` no dedicated test file | `test_pipeline_context.py` | None | 11 tests |
| ✅ PASS | `test_pipeline_fsm.py` all happy-path | — | — | Same as finding #1 — resolved |
| ❌ FAIL | `src/factory.py` has no test file | — | `src/factory.py` | `tests/unit/test_factory.py` does not exist. Called out in original review but FIX_PLAN.md dropped it from the 1.5 files list |
| ⏭️ DEFERRED | Frontend has zero test files | `frontend/src/**` | 35 files | Per FIX_PLAN.md |
| ⏭️ DEFERRED | `get_workflow_audit` / `get_workflow_dag` untested | API tests | — | Per FIX_PLAN.md |
| ⏭️ DEFERRED | `test_logging.py` weak assertions | — | — | Per FIX_PLAN.md |
| ⏭️ DEFERRED | `test_mcp.py` only 2 tests | — | — | Per FIX_PLAN.md |
| ⏭️ DEFERRED | `test_pipeline_scenarios.py` no malformed YAML tests | — | — | Per FIX_PLAN.md |

### 5. Documentation & Cognitive Debt

| Status | Original Finding | Files Checked | Files Still Affected | Details |
|--------|-----------------|---------------|----------------------|---------|
| ✅ PASS | `derivation_runner.py` 287 lines | — | — | Now 135L |
| ✅ PASS | `orchestrator.py` 282L + class 230L | — | — | Deleted |
| ⚠️ PARTIAL | `models.py` 254 lines | `models.py` | `models.py` | Reduced 254→201L; still 1L over hard limit |
| ✅ PASS | `workflow_manager.py` 251 lines | — | — | Now 189L; class 145L |
| ✅ PASS | `WorkflowDetailPage.tsx` 211 lines | — | — | Now 65L |
| ⚠️ PARTIAL | Dead orchestrator refs | `pipeline_fsm.py:12`, `test_pipeline_equivalence.py:1,31` | 2 files | Only docstring/comment mentions; no live imports or call sites. Acceptable, but could be scrubbed |
| ✅ PASS | CORS wildcard | `app.py` | — | Fixed |
| ✅ PASS | `COMPOSITION_LAYER.md` cross-reference | `ARCHITECTURE.md` | — | Line 170 |
| ✅ PASS | `ARCHITECTURE.md` sections | `ARCHITECTURE.md` | — | All 7 required sections present |
| ✅ PASS | `decisions.md` has ADR entries | `decisions.md` | — | 10 ADR entries |
| ✅ PASS | `REVIEW_FIX_LOG.md` + `REFACTORING.md` exist | root | — | Both present |
| ⏭️ DEFERRED | `workflows.py` 260L | — | `workflows.py` (255L) | Per FIX_PLAN.md |
| ⏭️ DEFERRED | `DataTab.tsx` 200L | — | `DataTab.tsx` (200L) | Per FIX_PLAN.md |
| ⏭️ DEFERRED | No Alembic | — | — | Per FIX_PLAN.md |

### 6. Tooling Verification

| Tool | Status | Errors | Warnings | Key Issues |
|------|--------|--------|----------|------------|
| `pyright src/` | ✅ Pass | 0 | 0 | Strict mode clean (src/ scope) |
| `ruff check src/ tests/` | ✅ Pass | 0 | 0 | All checks passed |
| `lint-imports` | ✅ Pass | 0 | 0 | 21 contracts kept, 0 broken |
| `check_enum_discipline.py` | ✅ Pass | 0 | 0 | 53 files, 0 violations |
| `pytest -q` | ✅ Pass | 0 | — | 234/234 passing |

Note: Running `pyright .` on the entire repo reports 61 errors in `scripts/validate_adam.py` and `tools/pre_commit_checks/_base.py`. These are **pre-existing** on the clean branch and **unrelated** to this review cycle. They're in helper/script code outside `src/`, not caught by CI which runs against `src/` only.

## Remaining Gaps (for /heal-review)

### Gap 1: `workflow_manager.py:40` except Exception without re-raise or justification
- **Category:** Typing & Style (Critical)
- **Original finding:** `except Exception` swallowed silently — no re-raise, destroys debugging info
- **Current state:** Line 40 catches the exception, logs via `logger.exception(...)`, rolls back the session, then **returns** without re-raising. No `# noqa` / comment justifying intentional swallow.
- **Remaining work:** Either (a) re-raise after the rollback, OR (b) add an inline comment: `# Intentionally swallowed: caller treats delete as best-effort idempotent` (or whatever the semantic is).
- **Files affected:** `src/api/workflow_manager.py:40`

### Gap 2: `src/domain/models.py` still 1 line over hard limit
- **Category:** Typing & Style + Documentation (Critical)
- **Original finding:** File >200 lines
- **Current state:** Reduced 254→201 (was supposed to be <150 per FIX_PLAN.md, but target was relaxed at review time to <200). Still 1L over the 200-line hard limit.
- **Remaining work:** Options:
  1. Trim the `__all__` list by removing backward-compat re-exports that aren't actually used externally (grep callers first)
  2. Move one of the simpler Pydantic models (e.g., `SpecSummary`) to a new `src/domain/spec_models.py`
  3. Accept and raise the hard limit to 210 in `REFACTORING.md` with justification
- **Files affected:** `src/domain/models.py`

### Gap 3: `tests/unit/test_factory.py` does not exist
- **Category:** Testing (Critical)
- **Original finding:** `src/factory.py` has no test file — factory functions untested
- **Current state:** File not created. FIX_PLAN.md dropped it from Fix Unit 1.5's file list, but the original review finding is still valid.
- **Remaining work:** Create `tests/unit/test_factory.py` with tests for `create_pipeline_orchestrator()`, `load_agent_configs()`, and any other public factory functions. At minimum: 1 happy path per factory, 1 error path for missing/malformed config.
- **Files affected:** `tests/unit/test_factory.py` (new), potentially `tests/conftest.py` for fixtures

### Gap 4: `.importlinter` stale Phase 4 comment
- **Category:** Architecture & SoC (Warning)
- **Original finding:** Stale comments about Phase 4 contracts being "commented out"
- **Current state:** Line 91 still has the stale NOTE ("engine-no-persistence contract will be added in Phase 4 when...") even though those contracts are active and passing.
- **Remaining work:** Remove or update the comment block at line 91 to reflect current state.
- **Files affected:** `.importlinter`

### Gap 5: `api-no-persistence` ignore_imports documentation
- **Category:** Architecture & SoC (Warning — partial)
- **Original finding:** Implicit — while the contract exists and lint-imports passes, the `ignore_imports` entries permit `src.api.app` + `src.api.workflow_manager` → persistence imports.
- **Current state:** These are legitimate design decisions (manager owns persistence lifecycle, app wires DB session factory) but aren't documented as such.
- **Remaining work:** Add a comment block above the `ignore_imports` entries explaining the rationale: "These are architectural exceptions — the WorkflowManager legitimately owns session lifecycle (mirrors the Repository pattern), and app.py wires the database at startup. Routers MUST NOT import persistence directly."
- **Files affected:** `.importlinter`

### Gap 6: Dead orchestrator mentions in docstrings/comments
- **Category:** Documentation & Debt (Partial)
- **Original finding:** `DerivationOrchestrator` / `WorkflowFSM` / `orchestrator_helpers` dead code
- **Current state:** All live code removed. Two docstring/comment mentions remain:
  - `src/engine/pipeline_fsm.py:12` — docstring says "unlike WorkflowFSM from the old architecture..."
  - `tests/integration/test_pipeline_equivalence.py:1,31` — comments reference `DerivationOrchestrator` historically
- **Remaining work:** Either keep as historical context (defensible) or scrub for cleanliness. Low priority.
- **Files affected:** 2 files above

## Deferred Items (not in scope for /heal-review)

These items are intentionally postponed per `FIX_PLAN.md`. They should NOT trigger `/heal-review` and are tracked in `REFACTORING.md` / future phases.

| Item | Category | Reason for Deferral |
|------|----------|---------------------|
| Frontend test suite (Vitest + RTL) | Testing | Large scope — separate initiative |
| Type API schema status fields as StrEnum | State & Enums | Requires coordinated backend+frontend change across all consumers |
| Frontend typed `as const` status unions | State & Enums | Depends on schema typing |
| Split `useWorkflows.ts` into domain hooks | Architecture | Low urgency — functional as-is |
| Move SpecsPage YAML to TanStack Query | State & Enums | Minor UX improvement |
| Extract DataTab → DatasetPanel | Docs & Debt | At boundary (200L), not over |
| Extract `workflows.py` helpers to presenter | Architecture / Typing | Addressed partially by Fix Unit 1.3 — file still 255L |
| Add Vitest CI gate | Testing | Requires frontend tests first |
| Alembic migration setup | Docs & Debt | Production concern, not homework scope |
| Introduce `DerivationRunContext` dataclass | Typing | Tied to derivation_runner split (already done) |
| `list_workflows` / `get_workflow_audit` pagination | Architecture | Not in FIX_PLAN.md scope |
| `step_builtins.py` open/closed refactor | Architecture | Not in FIX_PLAN.md scope |
| `verify_derivation` / `_compare_outputs` 7 params | Typing | Not in FIX_PLAN.md scope |
| API schemas str → StrEnum (5 fields) | State & Enums | Coordinated change deferred |
| `PipelineStepOut.type` / `AuditRecordOut` bare str | State & Enums | Known compromises |
| `test_logging.py` / `test_mcp.py` assertions | Testing | Not in FIX_PLAN.md scope |
| `test_pipeline_scenarios.py` malformed YAML tests | Testing | Not in FIX_PLAN.md scope |
| `get_workflow_audit` / `get_workflow_dag` endpoint tests | Testing | Not in FIX_PLAN.md scope |
| `SpecsPage.tsx` useState → TanStack Query | State & Enums | Per FIX_PLAN.md |
