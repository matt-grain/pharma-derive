# Architecture Review — CDDE (Clinical Data Derivation Engine)

**Date:** 2026-04-10
**Project type:** Python/FastAPI backend + Vite/React frontend

## Executive Summary

| Category | Conformance | Critical | Warnings | Info |
|----------|------------|----------|----------|------|
| Architecture & SoC | Medium | 4 | 5 | 5 |
| Typing & Style | Medium | 2 | 7 | 5 |
| State & Enums | Low | 6 | 8 | 2 |
| Testing | Low | 3 | 5 | 0 |
| Documentation & Debt | High | 0 | 3 | 3 |

### Top Critical Findings

1. **Enum discipline** — Raw strings `"review"`, `"human_approved"`, `"human"`, `"unknown"`, `"running"` used where StrEnum members exist. AuditRecord.action/agent typed as `str` not enum. (State & Enums)
2. **Frontend has zero tests** — 29 React components/pages/hooks with no Vitest, no RTL, no test files. (Testing)
3. **Orchestrator `run()` untested** — The core execution path has no unit test. Only constructor/property tests exist. (Testing)
4. **WorkflowManager bypasses repositories** — Direct SQLAlchemy queries in API layer via deferred imports, circumventing the repository pattern. (Architecture)
5. **API endpoint missing `response_model`** — POST /approve has no schema enforcement. (Architecture)

## Detailed Findings

### 1. Architecture & Separation of Concerns

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|----------|---------|---------|---------------|----------------|
| 🔴 | WorkflowManager issues raw SQLAlchemy queries (load_history, delete_workflow) bypassing repositories | `src/api/workflow_manager.py:50-56,137-143` | Repository pattern | Route through WorkflowStateRepository |
| 🔴 | POST /approve missing response_model | `src/api/routers/workflows.py:58` | Explicit response_model | Add `response_model=WorkflowStatusResponse` |
| 🔴 | GET /adam missing response_model (FileResponse exempt but inconsistent) | `src/api/routers/workflows.py:166` | Explicit response_model | Add `response_class=FileResponse` |
| 🔴 | API layer holds DerivationOrchestrator references directly | `src/api/workflow_manager.py` | Layered architecture | Consider thin WorkflowService interface |
| 🟡 | API schemas use raw `str` for enum fields (status, action, agent, qc_verdict) | `src/api/schemas.py` | Enum discipline | Use StrEnum types |
| 🟡 | CORS defaults to `"*"` | `src/config/settings.py:28` | Security | Default to localhost |
| 🟡 | Flat Settings class — secrets alongside structural config | `src/config/settings.py` | Separate settings per concern | Split into DatabaseSettings, LLMSettings, APISettings |
| 🟡 | GET /workflows/ returns unbounded list — no pagination | `src/api/routers/workflows.py:52-55` | Pagination required | Add limit/offset params |
| 🟡 | GET /specs/ reads all YAML from disk per request — no caching | `src/api/routers/specs.py:17-38` | Performance | Add lru_cache or background refresh |
| 🔵 | factory.py at src/ root — ambiguous layer ownership | `src/factory.py` | Module cohesion | Move to src/engine/ |
| 🔵 | WorkflowDetailPage 163 lines — above 50-line page rule | `frontend/src/pages/WorkflowDetailPage.tsx` | Thin pages | Extract WorkflowDetailView feature component |
| 🔵 | Frontend API client uses raw Error — no typed ApiError class | `frontend/src/lib/api.ts` | Typed error classes | Define ApiError with statusCode |
| 🔵 | Dashboard filters use inline raw string arrays `['completed', 'failed']` | `frontend/src/pages/DashboardPage.tsx:13` | Typed constants | Import TERMINAL_STATES from status.ts |
| 🔵 | DAGView uses inline status string literals for animated edges | `frontend/src/components/DAGView.tsx:45` | Centralize status checks | Add isActiveStatus() to status.ts |
| 🔵 | Domain and agent layers are clean — no import violations detected | All domain/agent files | N/A — compliant | ✅ |

### 2. Typing & Style

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|----------|---------|---------|---------------|----------------|
| 🔴 | DerivationOrchestrator.__init__ has 6 params | `src/engine/orchestrator.py:45-53` | Max 5 params | Extract OrchestratorConfig dataclass |
| 🔴 | verify_derivation (7 params), _compare_outputs (7), _handle_mismatch (7) | `src/verification/comparator.py`, `src/engine/derivation_runner.py` | Max 5 params | Group into VerificationRequest dataclass |
| 🟡 | `from __future__ import annotations` missing from 5 __init__.py files | `src/persistence/__init__.py`, `src/agents/tools/__init__.py`, etc. | Required in every .py file | Add to all |
| 🟡 | `Any` used without justification comment in 5 files | `src/domain/synthetic.py`, `executor.py`, `comparator.py`, `base_repo.py`, `spec_parser.py` | Any needs comment | Add inline justification |
| 🟡 | useEffect in DAGView has "what" comment not "why" comment | `frontend/src/components/DAGView.tsx:97` | WHY comments on useEffect | Explain why effect is needed |
| 🟡 | _SAFE_BUILTINS includes `print` — contradicts no-print rule | `src/agents/tools/sandbox.py:36` | No print in production | Remove from sandbox builtins |
| 🔵 | tsconfig.app.json has strict:true, noUncheckedIndexedAccess — exemplary | `frontend/tsconfig.app.json` | N/A — compliant | ✅ |
| 🔵 | All component props follow `<Name>Props` convention | `frontend/src/components/*.tsx` | N/A — compliant | ✅ |
| 🔵 | No bare `any` in TypeScript files | `frontend/src/` | N/A — compliant | ✅ |
| 🔵 | All Python functions have return type annotations | `src/**/*.py` | N/A — compliant | ✅ |
| 🔵 | All # type: ignore / # noqa have justification comments | `src/**/*.py` | N/A — compliant | ✅ |

### 3. State Management & Enums

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|----------|---------|---------|---------------|----------------|
| 🔴 | Raw string `"review"` in FSM state check | `src/engine/orchestrator.py:80` | Use WorkflowStep.REVIEW | Replace with enum member |
| 🔴 | Raw string `action="human_approved"` — no AuditAction enum member | `src/engine/orchestrator.py:84` | Missing enum member | Add AuditAction.HUMAN_APPROVED |
| 🔴 | Raw string `agent="human"` — no AgentName enum member | `src/engine/orchestrator.py:84` | Missing enum member | Add AgentName.HUMAN |
| 🔴 | AuditRecord.action and .agent typed as `str` not enum | `src/domain/models.py:202-203` | Enum discipline | Narrow to AuditAction / AgentName |
| 🔴 | `WorkflowStep.COMPLETED.value` unwrapped unnecessarily | `src/engine/orchestrator_helpers.py:60` | Compare enum directly | Drop .value |
| 🔴 | Dynamic f-string `f"fail_from_{self.current_state_value}"` — fragile | `src/domain/workflow_fsm.py:86` | Type-safe FSM transitions | Map via WorkflowStep enum first |
| 🟡 | All API schema status/verdict fields are bare `str` | `src/api/schemas.py` | Enum at boundary | Use StrEnum types |
| 🟡 | `status="running"` sentinel — no enum member exists | `src/api/routers/workflows.py:47` | No string sentinels | Use real FSM state or add enum |
| 🟡 | Multiple `"unknown"` fall-through sentinels | Various API routers | No string sentinels | Add WorkflowStep.UNKNOWN or raise |
| 🟡 | QCVerdict.MATCH.value unwrap in Streamlit UI | `src/ui/pages/workflow.py:101,114` | Compare directly | Drop .value |
| 🟡 | TERMINAL_STATES duplicated across 3 frontend files | hooks, DashboardPage, WorkflowDetailPage | DRY | Single export from status.ts |
| 🟡 | WorkflowStatus and WorkflowStep overlap (completed, failed) | `src/domain/workflow_models.py`, `models.py` | Single source of truth | Collapse into WorkflowStep |
| 🟡 | AuditTrail.record() accepts any string — enum not enforced | `src/audit/trail.py:21-26` | Enum discipline | Narrow params to enum types |
| 🟡 | Frontend status.ts missing several WorkflowStep values | `frontend/src/lib/status.ts` | Complete mapping | Add created, spec_review, dag_built, etc. |
| 🔵 | Engine layer enum usage (derivation_runner, comparator) is fully compliant | Business logic files | N/A — compliant | ✅ |
| 🔵 | TanStack Query used correctly for all server state | `frontend/src/hooks/useWorkflows.ts` | N/A — compliant | ✅ |

### 4. Testing Quality

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|----------|---------|---------|---------------|----------------|
| 🔴 | Frontend has zero tests — no Vitest, no RTL | `frontend/` | Every module needs tests | Add Vitest + @testing-library/react |
| 🔴 | orchestrator_helpers.py has no test file | `src/engine/orchestrator_helpers.py` | Every module gets tests | Create test_orchestrator_helpers.py |
| 🔴 | Orchestrator.run() completely untested | `tests/unit/test_orchestrator.py` | Happy + error path per function | Test with TestModel/FunctionModel |
| 🟡 | WorkflowManager: 4/9 public methods untested | `tests/unit/test_workflow_manager.py` | Coverage gaps | Add load_history, delete, is_known tests |
| 🟡 | 3/7 API endpoints untested (approve, delete, list) | `tests/unit/test_api.py` | Every endpoint covered | Add endpoint tests |
| 🟡 | FSM tests only one invalid transition — need full matrix | `tests/unit/test_workflow_fsm.py` | All invalid transitions tested | Parametrize all (state, invalid_event) pairs |
| 🟡 | pytest.raises without match= in 4 locations | Various test files | Specific exception matching | Add match= patterns |
| 🟡 | src/ui/ (Streamlit) has zero tests | `src/ui/` | Module test coverage | Document as waived or add smoke tests |

**Testing Positives:**
- AAA pattern: 401 comment occurrences across 167 tests — exceptionally consistent
- Sandbox security tests: dedicated tests for import/open/eval/exec blocking
- FSM fail transitions: fully parametrized across all states
- conftest fixtures: well-structured factories prevent magic data

### 5. Documentation & Cognitive Debt

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|----------|---------|---------|---------------|----------------|
| 🟡 | CORS wildcard `"*"` as default | `src/config/settings.py:28` | Security | Default to localhost |
| 🟡 | 3 files over 200 lines: orchestrator (269), workflows router (256), models (249) | Various | Module size | Split enums to enums.py, extract router helpers |
| 🟡 | No Alembic — schema via create_all() only | `src/persistence/database.py` | Migration management | Add Alembic for production |
| 🔵 | Zero TODO/FIXME/HACK comments | All files | N/A — compliant | ✅ |
| 🔵 | All 42 type:ignore/noqa have inline justification | All files | N/A — compliant | ✅ |
| 🔵 | ARCHITECTURE.md has all 7 required sections | `/ARCHITECTURE.md` | N/A — compliant | ✅ |
| 🔵 | decisions.md has 9 well-structured ADRs | `/decisions.md` | N/A — compliant | ✅ |
| 🔵 | Dependencies properly pinned with >=X,<N+1 bounds | `pyproject.toml` | N/A — compliant | ✅ |
| 🔵 | Both lockfiles committed (uv.lock, package-lock.json) | Root | N/A — compliant | ✅ |

## Migration Plan

### Phase 0 — Quick Wins (mechanical, low risk)
- [ ] Add `AuditAction.HUMAN_APPROVED` and `AgentName.HUMAN` enum members
- [ ] Replace `"review"` with `WorkflowStep.REVIEW` in orchestrator.py:80
- [ ] Drop `.value` from `WorkflowStep.COMPLETED.value` in orchestrator_helpers.py:60
- [ ] Add `response_model=WorkflowStatusResponse` to POST /approve endpoint
- [ ] Add `from __future__ import annotations` to 5 __init__.py files
- [ ] Add `Any` justification comments to 5 bare imports
- [ ] Change CORS default from `"*"` to `"http://localhost:3000"`
- [ ] Export TERMINAL_STATES from status.ts, import in Dashboard/Detail pages
- [ ] Add missing WorkflowStep values to frontend status.ts

### Phase 1 — Structural Improvements (medium effort)
- [ ] Route WorkflowManager DB queries through WorkflowStateRepository
- [ ] Narrow AuditRecord.action/agent to enum types
- [ ] Replace raw `str` fields in API schemas with StrEnum types
- [ ] Add `match=` to all bare pytest.raises calls
- [ ] Create test_orchestrator_helpers.py
- [ ] Add tests for approve/delete/list API endpoints
- [ ] Add Vitest + RTL to frontend with smoke tests
- [ ] Parametrize full FSM invalid transition matrix
- [ ] Extract OrchestratorConfig dataclass (reduce 6-param __init__)

### Phase 2 — Architectural Changes (higher effort)
- [ ] Collapse WorkflowStatus into WorkflowStep (single source of truth)
- [ ] Test Orchestrator.run() with TestModel/FunctionModel
- [ ] Add Alembic migration infrastructure
- [ ] Split Settings into DatabaseSettings/LLMSettings/APISettings
- [ ] Add pagination to GET /workflows/ endpoint
- [ ] Move YAML spec content fetch to TanStack Query (not useState)
- [ ] Extract WorkflowDetailView feature component (thin page)

### Phase 3 — Ongoing Discipline
- [ ] Add eslint-plugin-boundaries for frontend import rules
- [ ] Add frontend test CI gate (vitest run)
- [ ] Monitor orchestrator_helpers.py for catch-all growth
- [ ] Document Streamlit UI as deprecated (replaced by React SPA)
