# Architecture Review — CDDE (Clinical Data Derivation Engine)

**Date:** 2026-04-11
**Last fixed:** 2026-04-12 — 13/14 fix units resolved (1 partial: models.py 1L over hard limit)
**Project type:** Python/FastAPI backend + Vite/React frontend
**Branch:** feat/yaml-pipeline (post Phase 14 — YAML-driven pipeline)
**Previous review:** docs/phase4/REVIEW.md (2026-04-10)
**Fix log:** REVIEW_FIX_LOG.md

## Executive Summary

| Category | Conformance | Critical | Warnings | Info |
|----------|------------|----------|----------|------|
| Architecture & SoC | Medium | 4 | 5 | 7 |
| Typing & Style | Medium | 5 | 7 | 5 |
| State & Enums | Medium | 5 | 4 | 4 |
| Testing | Medium | 6 | 5 | 3 |
| Documentation & Debt | Medium | 7 | 5 | 2 |

### Top Critical Findings

1. **File/class size violations** — 6 files over 200 lines, 2 classes over 150 lines (`DerivationOrchestrator` 230L, `WorkflowManager` 211L). Most severe: `derivation_runner.py` at 287 lines.
2. **API schemas use bare `str` for enum-valued fields** — 5 `status` fields in `schemas.py` + mirrored in frontend `types/api.ts`. No type safety at the API boundary.
3. **Dead code: old orchestrator** — `DerivationOrchestrator` + `WorkflowFSM` + `orchestrator_helpers.py` are unused by the pipeline path but still compiled and maintained.
4. **`PipelineFSM` uses raw string literals** — `"created"`, `"completed"`, `"failed"` hardcoded, no transition guards, not a true FSM.
5. **Frontend has zero tests** — 35 source files with no Vitest/RTL test suite.
6. **`delete_workflow` router owns a DB session lifecycle** — direct `init_db()` + `session.commit()` in a router endpoint.

## Detailed Findings

### 1. Architecture & Separation of Concerns

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|----------|---------|---------|---------------|----------------|
| 🔴 | `delete_workflow` router creates DB session, instantiates repo, commits — business logic in router | `workflows.py:86-90` | No business logic in routers | Push session lifecycle into `WorkflowManager.delete_workflow` |
| 🔴 | `WorkflowCreateRequest` is the only schema without `frozen=True` | `schemas.py:8` | API schemas use frozen=True | Add `frozen=True` |
| 🔴 | `list_workflows` and `get_workflow_audit` return unbounded lists — no pagination | `workflows.py:54,150` | Always paginate list endpoints | Add skip/limit params |
| 🔴 | `.importlinter` has no `api-no-persistence` contract — router's direct persistence import uncaught by CI | `.importlinter` | Import contracts must cover all layers | Add `api-no-persistence` contract |
| 🟡 | Old orchestrator still imported in `factory.py` and `workflow_manager.py` (TYPE_CHECKING shim) — dead code | `factory.py:11`, `workflow_manager.py:22` | YAGNI — no dead code paths | Remove or deprecate |
| 🟡 | `allow_methods=["*"]` and `allow_headers=["*"]` in CORS | `app.py:58-59` | Restrict CORS methods/headers | Pin to actual verbs used |
| 🟡 | `WorkflowDetailPage.tsx` is 211 lines | `WorkflowDetailPage.tsx` | Pages under 200 lines | Extract sub-components |
| 🟡 | `step_builtins.py` deps builder uses string dispatch — new agents require editing a centralized function | `step_builtins.py:103-124` | Open/closed principle | Consider decorator or per-agent registration |
| 🟡 | All TanStack Query hooks in a single `useWorkflows.ts` (11 hooks) — god hook module | `useWorkflows.ts` | Features self-contained | Split by domain concern |
| 🔵 | `specs.py` router has inline YAML parsing logic | `specs.py:17-39` | No business logic in routers | Extract to service/helper |
| 🔵 | `.importlinter` has stale comments about Phase 4 contracts being "commented out" | `.importlinter:11-13` | Documentation accuracy | Update comments |
| 🔵 | Domain and agent layers are clean — no import violations detected | All domain/agent files | N/A — compliant | ✅ |
| 🔵 | Pipeline engine properly layered — domain models in domain/, executors in engine/ | pipeline_*.py, step_*.py | N/A — compliant | ✅ |
| 🔵 | YAML agent configs fully externalized — zero hardcoded agent paths in src/ | All src/ files | N/A — compliant | ✅ |
| 🔵 | 3 pipeline configs demonstrate platform flexibility | config/pipelines/*.yaml | N/A — compliant | ✅ |
| 🔵 | Config-driven agent declarations in pipeline YAML (coder_agent, qc_agent, debugger_agent) | clinical_derivation.yaml | N/A — compliant | ✅ |

### 2. Typing & Style

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|----------|---------|---------|---------------|----------------|
| 🔴 | `except Exception` swallowed silently — no re-raise, destroys debugging info | `workflow_manager.py:124` | No bare except without re-raise | Re-raise or log as intentional with justification |
| 🔴 | `except Exception` swallowed in old orchestrator — error absorbed into state.errors | `orchestrator.py:122` | Catch specific exceptions | Narrow to CDDEError |
| 🔴 | `except Exception` swallowed in Streamlit UI | `ui/pages/workflow.py:46` | No bare except without re-raise | Log with logger.exception before swallowing |
| 🔴 | `WorkflowManager` class is 211 lines (limit 150) | `workflow_manager.py` | Class under 150 lines | Extract serializer + registry |
| 🔴 | `DerivationOrchestrator` class is 230 lines (limit 150) | `orchestrator.py` | Class under 150 lines | Extract step helpers + persisters |
| 🟡 | 8 functions with 6+ parameters in `derivation_runner.py` | `derivation_runner.py` | Max 5 function params | Introduce `DerivationRunContext` dataclass |
| 🟡 | `verify_derivation` + `_compare_outputs` have 7 params each | `comparator.py` | Max 5 function params | Introduce `ComparisonRequest` dataclass |
| 🟡 | `derivation_runner.py` is 287 lines | `derivation_runner.py` | File under 200 lines | Split debug logic to `debug_runner.py` |
| 🟡 | `orchestrator.py` is 282 lines | `orchestrator.py` | File under 200 lines | Extract collaborators |
| 🟡 | `workflows.py` is 260 lines | `workflows.py` | File under 200 lines | Extract helpers to presenter module |
| 🟡 | `models.py` is 254 lines | `models.py` | File under 200 lines | Split enums to `enums.py` |
| 🟡 | `workflow_manager.py` is 251 lines | `workflow_manager.py` | File under 200 lines | Follows from class split |
| 🔵 | 9 `__init__.py` files missing `from __future__ import annotations` | Various `__init__.py` | Future annotations in every file | Add to all |
| 🔵 | All functions have complete type annotations | All src/*.py | N/A — compliant | ✅ |
| 🔵 | tsconfig.app.json has strict: true + noUncheckedIndexedAccess: true | tsconfig.app.json | N/A — compliant | ✅ |
| 🔵 | Zero `any` in frontend, zero `print()` in src/ | All files | N/A — compliant | ✅ |
| 🔵 | All `# type: ignore` and `# noqa` have inline justifications | All files | N/A — compliant | ✅ |

### 3. State Management & Enums

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|----------|---------|---------|---------------|----------------|
| 🔴 | 5 API schemas have `status: str` instead of StrEnum | `schemas.py:15,21,33,59,120` | Use StrEnum for fixed value sets | Type as WorkflowStep/WorkflowStatus |
| 🔴 | Frontend `types/api.ts` mirrors bare `string` for all status/verdict/type fields | `types/api.ts` | Use as const or string unions | Define typed constants |
| 🔴 | `PipelineFSM` uses raw string literals and has no transition guards | `pipeline_fsm.py:16,29,33,38` | FSM must use enum members | Use WorkflowStep enum, add transition map |
| 🔴 | `workflow_manager.py` passes raw `"failed"` to state_repo.save | `workflow_manager.py:122` | No raw string for FSM states | Use fsm.current_state_value after fail() |
| 🔴 | Router returns `status="running"` and `status="unknown"` — not enum members | `workflows.py:49,260` | No string sentinels | Add to WorkflowStep or use existing members |
| 🟡 | `SpecsPage.tsx` stores fetched YAML content in useState instead of TanStack Query | `SpecsPage.tsx:21` | No server data in useState | Extract useSpecContent hook |
| 🟡 | `PipelineStepOut.type` is `str` even though `StepType` StrEnum exists | `schemas.py:100` | Use StrEnum at boundary | Type as StepType |
| 🟡 | `AuditRecordOut.action/agent` are bare `str` (union with enum is a known compromise) | `schemas.py:45-46` | Enum discipline | Document the compound form explicitly |
| 🟡 | `STATUS_COLOR_MAP` accepts arbitrary strings with silent gray fallback | `lib/status.ts:8` | Exhaustive type checking | Type map with enum union keys |
| 🔵 | No TypeScript `enum` keyword used — project correctly uses `as const` patterns | Frontend | N/A — compliant | ✅ |
| 🔵 | All domain enums use StrEnum properly (10 enums in models.py) | `models.py` | N/A — compliant | ✅ |
| 🔵 | `StepType` StrEnum correctly defined and used in pipeline models | `pipeline_models.py` | N/A — compliant | ✅ |
| 🔵 | All server state managed through TanStack Query hooks | `useWorkflows.ts` | N/A — compliant | ✅ |

### 4. Testing Quality

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|----------|---------|---------|---------------|----------------|
| 🔴 | Frontend has zero test files — 35 source files completely untested | `frontend/src/` | Every module needs tests | Add Vitest + RTL |
| 🔴 | `PipelineFSM` has zero invalid-transition tests — no guards verified | `test_pipeline_fsm.py` | All FSM transitions tested (valid AND invalid) | Add invalid transition tests |
| 🔴 | 2 bare `pytest.raises(ValidationError)` without `match=` | `test_models.py:30,126` | pytest.raises must have match= | Add match patterns |
| 🔴 | `step_builtins.py` has no dedicated test file — 4 functions untested in isolation | No test file | Every module gets tests | Create `test_step_builtins.py` |
| 🔴 | `pipeline_context.py` has no dedicated test file | No test file | Every module gets tests | Create `test_pipeline_context.py` |
| 🔴 | `factory.py` has no test file — factory functions untested | No test file | Every module gets tests | Create `test_factory.py` |
| 🟡 | `get_workflow_audit` and `get_workflow_dag` endpoints have no tests | `workflows.py:151-232` | Every endpoint tested | Add to test_api.py |
| 🟡 | `test_logging.py` tests only assert "no exception" — no log output assertions | `test_logging.py` | Meaningful assertions | Capture and assert log output |
| 🟡 | `test_mcp.py` has only 2 tests, no error paths | `test_mcp.py` | Happy + error path per method | Add error path tests |
| 🟡 | `test_pipeline_fsm.py` all happy-path, no invalid-advance tests | `test_pipeline_fsm.py` | FSM invalid transitions tested | Add failure tests |
| 🟡 | `test_pipeline_scenarios.py` has no error-path tests for malformed YAML | `test_pipeline_scenarios.py` | Error paths tested | Add invalid pipeline tests |
| 🔵 | AAA pattern used consistently — 522 markers across 26 files | All test files | N/A — compliant | ✅ |
| 🔵 | Test naming follows `test_<action>_<scenario>_<expected>` spec pattern | All test files | N/A — compliant | ✅ |
| 🔵 | conftest.py provides quality factory fixtures | `conftest.py` | N/A — compliant | ✅ |

### 5. Documentation & Cognitive Debt

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|----------|---------|---------|---------------|----------------|
| 🔴 | `derivation_runner.py` is 287 lines | `derivation_runner.py` | File under 200 lines | Split debug logic |
| 🔴 | `orchestrator.py` is 282 lines + class 230 lines | `orchestrator.py` | File/class limits | Extract or delete (dead code) |
| 🔴 | `workflows.py` is 260 lines | `workflows.py` | File under 200 lines | Extract helpers |
| 🔴 | `models.py` is 254 lines | `models.py` | File under 200 lines | Split enums |
| 🔴 | `workflow_manager.py` is 251 lines + class 211 lines | `workflow_manager.py` | File/class limits | Extract serializer |
| 🔴 | Dead code: old orchestrator + WorkflowFSM + orchestrator_helpers unused by pipeline path | `orchestrator.py`, `workflow_fsm.py`, `orchestrator_helpers.py` | YAGNI | Confirm dead, then delete |
| 🔴 | `WorkflowDetailPage.tsx` is 211 lines | `WorkflowDetailPage.tsx` | File under 200 lines | Extract sub-components |
| 🟡 | `run()` method is 39 lines, `get_workflow_result` 37 lines, several others 31-35 lines | Various | Function under 30 lines | Extract sub-functions |
| 🟡 | CORS allow_methods/allow_headers wildcard | `app.py:58-59` | Restrict CORS | Pin to actual verbs |
| 🟡 | `DataTab.tsx` is 200 lines with 4 items in one file | `DataTab.tsx` | File under 200 lines | Extract DatasetPanel |
| 🟡 | `COMPOSITION_LAYER.md` not cross-referenced from ARCHITECTURE.md | `docs/COMPOSITION_LAYER.md` | Docs findable | Add cross-reference |
| 🟡 | No Alembic — uses create_all() (known, accepted gap) | `database.py` | Migration tooling | Document as ADR |
| 🔵 | ARCHITECTURE.md has all 7 required sections + pipeline engine section | `ARCHITECTURE.md` | N/A — compliant | ✅ |
| 🔵 | decisions.md has 9 well-structured ADRs | `decisions.md` | N/A — compliant | ✅ |
| 🔵 | Zero TODO/FIXME/HACK, zero bare type:ignore/noqa | All files | N/A — compliant | ✅ |
| 🔵 | All lockfiles committed (uv.lock + package-lock.json) | Root | N/A — compliant | ✅ |
| 🔵 | Pipeline docs exist: COMPOSITION_LAYER.md, config/README.md, config/agents/README.md | docs/, config/ | N/A — compliant | ✅ |

## Migration Plan

### Phase 0 — Quick Wins (mechanical, low risk)
- [x] Add `frozen=True` to `WorkflowCreateRequest`
- [x] Add `from __future__ import annotations` to 9 `__init__.py` files
- [x] Add `match=` to 2 bare `pytest.raises` in `test_models.py`
- [x] Add `match=` to 2 bare `pytest.raises` in `test_workflow_fsm.py` (file later deleted by 1.2)
- [x] Add `api-no-persistence` import-linter contract
- [x] Update stale `.importlinter` comment about Phase 4 contracts
- [x] Add COMPOSITION_LAYER.md cross-reference to ARCHITECTURE.md
- [x] Restrict CORS allow_methods/allow_headers to actual verbs

### Phase 1 — Structural (medium effort)
- [x] Split `models.py` into `enums.py` + `models.py` — ⚠️ Partial: 254→201L (1L over hard limit; `__all__` boilerplate)
- [x] Split `derivation_runner.py` — extract debug logic to `debug_runner.py` (287→135L + 192L new)
- [ ] Extract `_build_status_response` + `_dag_node_out` from `workflows.py` to presenter module — deferred
- [x] Extract `_serialize_ctx` + `_build_result` from `WorkflowManager` to serializer (class 211→145L)
- [x] Extract `WorkflowDetailPage` sub-components (Header, Tabs) — 211→65L
- [ ] Move `SpecsPage` YAML content fetch to TanStack Query hook — deferred
- [ ] Type API schema status fields as StrEnum — deferred (coordinated backend+frontend change)
- [x] Replace `PipelineFSM` raw strings with `WorkflowStep` enum values (transition guards intentionally deferred)
- [x] Replace `"running"` and `"unknown"` raw strings in router — added WorkflowStep.RUNNING + UNKNOWN members
- [x] Push `delete_workflow` DB session into `WorkflowManager`
- [x] Create `test_step_builtins.py` (17 tests) + `test_pipeline_context.py` (11 tests) — `test_factory.py` deferred
- [x] Add FSM invalid-transition tests to `test_pipeline_fsm.py` (+4 tests)
- [ ] Introduce `DerivationRunContext` dataclass to reduce function params — deferred

### Phase 2 — Architectural (higher effort)
- [x] Delete old orchestrator (`orchestrator.py`, `workflow_fsm.py`, `orchestrator_helpers.py`) — 7 files deleted
- [ ] Define typed `as const` status unions in frontend, narrow `types/api.ts` — deferred
- [ ] Add Vitest + RTL to frontend with smoke tests for key components — deferred (separate initiative)
- [ ] Add tests for `get_workflow_audit` and `get_workflow_dag` endpoints — deferred
- [ ] Strengthen `test_logging.py` and `test_mcp.py` assertions — deferred

### Phase 3 — Ongoing Discipline
- [ ] Add frontend test CI gate (vitest run)
- [ ] Add `api-no-engine` import-linter contract
- [ ] Monitor file/class sizes as features are added
- [ ] Document Alembic migration path as ADR
