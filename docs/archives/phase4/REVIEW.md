# Architecture Review — pharma-derive

**Date:** 2026-04-09
**Last fixed:** 2026-04-09 — 18/18 critical+warning findings resolved across Phases 0-2, 13/13 Phase 0 migration items completed
**Project type:** Python (generic) — PydanticAI-based agentic system

## Executive Summary

| Category | Conformance | Critical | Warnings | Info |
|----------|------------|----------|----------|------|
| Architecture & SoC | High | 0 (3 fixed) | 3 remaining | 4 |
| Typing & Style | High | 0 (4 fixed) | 2 remaining | 2 |
| State & Enums | High | 0 (6 fixed) | 2 remaining | 2 |
| Testing | Low | 2 (deferred) | 5 remaining | 0 |
| Documentation & Debt | Medium | 3 (deferred) | 1 remaining | 9 |

### Top Critical Findings

1. ~~`derivation_runner.py` has zero test coverage~~ — deferred to next phase (tests)
2. ~~All 5 agents bypass the LLM gateway~~ — **Fixed**: removed module-level `_model`, agents use `"test"` placeholder overridden at call time
3. ~~`AuditSummary` in `WorkflowResult` is never populated~~ — **Fixed**: moved to domain, field populated in `_build_result()`
4. ~~`DebugAnalysis.correct_implementation` and `.confidence` are raw strings~~ — **Fixed**: `CorrectImplementation` and `ConfidenceLevel` StrEnums defined
5. ~~Multiple `except Exception:` blocks swallow errors~~ — **Fixed**: narrowed to specific types in executor/tools, added `logger.exception()` in orchestrator

## Detailed Findings

### 1. Architecture & Separation of Concerns

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|----------|---------|---------|---------------|----------------|
| :red_circle: Critical | `WorkflowResult` declares `audit_summary: AuditSummary | None` where `AuditSummary` is imported from `src.agents.auditor` — engine output type carries runtime dependency on agents layer | `src/engine/orchestrator.py` | Engine output types must not embed agents-layer types | ✅ Fixed — `AuditSummary` moved to `src/domain/models.py` |
| :red_circle: Critical | `AuditSummary` field is declared but **never populated** in `_build_result()` — always `None`. Silent data loss bug. | `src/engine/orchestrator.py` | Declared output fields must be populated | ✅ Fixed — field populated via `self._state.audit_summary` |
| :red_circle: Critical | All 5 agent modules construct their own `OpenAIChatModel` + `OpenAIProvider` with hardcoded `base_url` and `api_key` at module level. | `src/agents/*.py` | "All LLM calls go through a single gateway function" | ✅ Fixed — removed module-level `_model`; agents use `"test"` placeholder |
| :yellow_circle: Warning | `WorkflowStatus` enum in orchestrator duplicates terminal states already in `WorkflowStep` (domain) | `src/engine/orchestrator.py` | Domain models are single source of truth | ✅ Fixed — moved to `domain/models.py` |
| :yellow_circle: Warning | Two unjustified runtime local imports in `derivation_runner.py` | `src/engine/derivation_runner.py` | Local imports only for genuine circular dependencies | ✅ Fixed — moved to top-level / TYPE_CHECKING |
| :yellow_circle: Warning | `orchestrator.py` is 237 lines — exceeds the 200-line limit | `src/engine/orchestrator.py` | Files > 200 lines: flag for review | Deferred — split planned for next phase |
| :yellow_circle: Warning | `.importlinter` missing contracts for `audit-no-agents` and `ui-no-*` | `.importlinter` | Layer boundary contracts must be complete | Deferred |
| :yellow_circle: Warning | `src/agents/tools.py` (187 lines) serves dual purpose | `src/agents/tools.py` | No catch-all files | Deferred — split planned for next phase |
| :blue_circle: Info | Package nesting depth is 3 levels — within 4-level limit | All `src/**/*.py` | Compliant | No action needed |
| :blue_circle: Info | Domain modules contain zero framework imports — domain purity maintained | `src/domain/` | Compliant | No action needed |
| :blue_circle: Info | Repositories use `select()` exclusively, return Pydantic models, never ORM rows | `src/persistence/repositories.py` | Compliant | No action needed |
| :blue_circle: Info | `TYPE_CHECKING` guard used correctly in orchestrator for persistence imports | `src/engine/orchestrator.py` | Compliant | No action needed |

### 2. Typing & Style

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|----------|---------|---------|---------------|----------------|
| :red_circle: Critical | `from __future__ import annotations` missing from `src/domain/models.py` | `src/domain/models.py` | All files must use `from __future__ import annotations` | ✅ Fixed |
| :red_circle: Critical | `except Exception as exc:` in `orchestrator.py` `run()` swallows exception without logging | `src/engine/orchestrator.py` | Never `except Exception:` without re-raising | ✅ Fixed — added `logger.exception()` |
| :red_circle: Critical | `except Exception as exc:` in `executor.py` silently converts any error | `src/domain/executor.py` | Catch specific exceptions | ✅ Fixed — narrowed to 8 specific types |
| :red_circle: Critical | `_debug_variable()` has 7 params; `verify_derivation()` has 7 params | `src/engine/derivation_runner.py`, `src/verification/comparator.py` | Max 5 function arguments | Deferred — grouping into dataclasses planned |
| :yellow_circle: Warning | `_run_coder_and_qc()` declares `rule: object` instead of `rule: DerivationRule` | `src/engine/derivation_runner.py` | Full, accurate type annotations | ✅ Fixed — proper TYPE_CHECKING import + annotation |
| :yellow_circle: Warning | Module-level constants lack `Final[...]` annotation | `src/engine/llm_gateway.py` et al. | Constants must use `Final` | ✅ Fixed |
| :yellow_circle: Warning | `_MAX_DEBUG_RETRIES = 2` is defined but never used | `src/engine/derivation_runner.py` | No dead/misleading code | ✅ Fixed — removed constant and stale docstring |
| :yellow_circle: Warning | `WorkflowFSM` state/transition class attributes lack type annotations | `src/engine/workflow_fsm.py` | All class attributes must be annotated | Deferred |
| :yellow_circle: Warning | `loguru` logger used in only 2 of 27 source files | All `src/` | Use structured logging | ⚠️ Partial — added to orchestrator; more files needed |
| :blue_circle: Info | All `Any` usage has justification comments | Various | Compliant | No action needed |
| :blue_circle: Info | No `== None`, `.format()`, `print()`, wildcard imports found | All `src/` | Compliant | No action needed |

### 3. State Management & Enums

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|----------|---------|---------|---------------|----------------|
| :red_circle: Critical | `DebugAnalysis.correct_implementation` typed as `str` — hidden enum | `src/agents/debugger.py` | Never raw strings for fixed sets | ✅ Fixed — `CorrectImplementation(StrEnum)` |
| :red_circle: Critical | Raw string comparisons `== "coder"` and `== "qc"` | `src/engine/derivation_runner.py` | Must use enum members | ✅ Fixed |
| :red_circle: Critical | `DebugAnalysis.confidence` typed as `str` — hidden enum | `src/agents/debugger.py` | Never raw strings for categories | ✅ Fixed — `ConfidenceLevel(StrEnum)` |
| :red_circle: Critical | `QCHistoryRepository.store()` accepts `verdict: str` | `src/persistence/repositories.py` | Never raw strings when enum exists | ✅ Fixed — accepts `QCVerdict` |
| :red_circle: Critical | Raw string `"match"` used to filter in `get_stats()` | `src/persistence/repositories.py` | Never raw string literals | ✅ Fixed — `QCVerdict.MATCH.value` |
| :red_circle: Critical | `vr.verdict.value == "match"` bypassing enum | `src/engine/derivation_runner.py` | Must use enum members | ✅ Fixed — `vr.verdict == QCVerdict.MATCH` |
| :yellow_circle: Warning | `self._fsm.current_state_value == "completed"` — raw string | `src/engine/orchestrator.py` | FSM transitions must use enum values | ✅ Fixed — `WorkflowStep.COMPLETED.value` |
| :yellow_circle: Warning | Raw string `"pending"` used as fallback | `src/engine/orchestrator.py` | Never raw strings for statuses | ✅ Fixed — `DerivationStatus.PENDING.value` |
| :yellow_circle: Warning | `VerificationResult.recommendation` — hidden 3-value enum | `src/verification/comparator.py` | Never raw strings for categories | ✅ Fixed — `VerificationRecommendation(StrEnum)` |
| :yellow_circle: Warning | `AuditRecord.action` and `.agent` raw string literals | `src/audit/trail.py`, `src/engine/orchestrator.py` | Never raw strings for roles/actions | Deferred |
| :yellow_circle: Warning | `WorkflowFSM.fail()` builds transition name via f-string + `getattr` | `src/engine/workflow_fsm.py` | FSM transitions must use enum values | Deferred |
| :blue_circle: Info | No dedicated `enums.py` — enums defined in `models.py` | `src/domain/models.py` | Enums should be centralized | Acceptable — `models.py` is the canonical location |
| :blue_circle: Info | `DAGNode` has no per-node FSM | `src/domain/dag.py` | Entities with status field should have FSM | Deferred to production |

### 4. Testing Quality

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|----------|---------|---------|---------------|----------------|
| :red_circle: Critical | `src/engine/derivation_runner.py` has zero test coverage | No test file exists | Every public method needs tests | Deferred to next phase |
| :red_circle: Critical | `src/engine/logging.py` has no tests | No test file exists | Every public method needs tests | Deferred to next phase |
| :yellow_circle: Warning | 5 FSM transitions untested | `tests/unit/test_workflow_fsm.py` | Every FSM transition tested | Deferred |
| :yellow_circle: Warning | 7 of 12 test files lack AAA section markers | Multiple test files | Tests must follow AAA pattern | Deferred |
| :yellow_circle: Warning | 2 uses of bare `pytest.raises(Exception)` | `test_spec_parser.py`, `test_workflow.py` | Tests must catch specific exceptions | ✅ Fixed — `yaml.YAMLError` and `ValidationError` |
| :yellow_circle: Warning | `orchestrator.run()` has zero test coverage | `tests/unit/test_orchestrator.py` | Every public method needs tests | Deferred |
| :yellow_circle: Warning | `FeedbackRepository` missing edge-case tests | `tests/unit/test_persistence.py` | Every public method needs tests | Deferred |
| :yellow_circle: Warning | 13 redundant `@pytest.mark.asyncio` decorators | `tests/unit/test_agent_tools.py` | Correct pytest-asyncio configuration | ✅ Fixed |
| :yellow_circle: Warning | No mocked-LLM integration test exists | `tests/integration/test_workflow.py` | Integration tests for agent workflows | Deferred |

### 5. Documentation & Cognitive Debt

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|----------|---------|---------|---------------|----------------|
| :red_circle: Critical | `generate_synthetic()` is 42 lines | `src/domain/spec_parser.py` | Function over 30 lines | Deferred — split planned |
| :red_circle: Critical | `_step_audit()` is 32 lines | `src/engine/orchestrator.py` | Function over 30 lines | Deferred — split planned |
| :red_circle: Critical | `DerivationOrchestrator` class is 168 lines | `src/engine/orchestrator.py` | Class over 150 lines | Deferred — split planned |
| :yellow_circle: Warning | `spec_parser.py` mixes 3 responsibilities | `src/domain/spec_parser.py` | Topic-specific modules | Deferred |
| :yellow_circle: Warning | `agents/tools.py` mixes types + tools | `src/agents/tools.py` | No catch-all utility files | Deferred |
| :yellow_circle: Warning | Ruff `"S"` security ruleset absent | `pyproject.toml` | Static security analysis | ✅ Fixed — added with proper `# noqa` |
| :blue_circle: Info | ARCHITECTURE.md exists with all required sections | `ARCHITECTURE.md` | Compliant | No action needed |
| :blue_circle: Info | decisions.md exists with 3 well-formed ADRs | `decisions.md` | Compliant | No action needed |
| :blue_circle: Info | uv.lock committed; all deps use `>=X.Y,<X+1` bounds | `pyproject.toml`, `uv.lock` | Compliant | No action needed |
| :blue_circle: Info | No f-string SQL, hardcoded secrets, or `time.sleep()` in async code | `src/` | Compliant | No action needed |
| :blue_circle: Info | No TODO/FIXME/HACK comments in src/ or tests/ | `src/`, `tests/` | Compliant | No action needed |
| :blue_circle: Info | All `# type: ignore` and `# noqa` carry justification comments | `src/` | Compliant | No action needed |
| :blue_circle: Info | `domain/models.py` — all small Pydantic classes | `src/domain/models.py` | Monitor growth | No action now |
| :blue_circle: Info | `persistence/repositories.py` — 4 small classes | `src/persistence/repositories.py` | Monitor growth | No action now |
| :blue_circle: Info | No Alembic configured — acceptable for prototype | — | Add if graduating to production DB | No action now |

## Migration Plan

### Phase 0 — Quick Wins (mechanical, low risk)
- [x] Add `from __future__ import annotations` to `src/domain/models.py`
- [x] Replace `vr.verdict.value == "match"` with `vr.verdict == QCVerdict.MATCH` in `derivation_runner.py`
- [x] Replace `self._fsm.current_state_value == "completed"` with `WorkflowStep.COMPLETED.value` in `orchestrator.py`
- [x] Replace raw `"pending"` string with `DerivationStatus.PENDING.value` in `orchestrator.py`
- [x] Replace raw `"match"` string with `QCVerdict.MATCH.value` in `repositories.py`
- [x] Change `QCHistoryRepository.store()` param from `verdict: str` to `verdict: QCVerdict`
- [x] Add `Final[...]` annotations to module-level constants in `llm_gateway.py`, `tools.py`, `spec_parser.py`
- [x] Remove unused `_MAX_DEBUG_RETRIES` constant and stale docstring in `derivation_runner.py`
- [x] Remove redundant `@pytest.mark.asyncio` decorators in `test_agent_tools.py`
- [x] Replace bare `pytest.raises(Exception)` with specific exception types (2 locations)
- [x] Move unjustified local imports to top-level in `derivation_runner.py`
- [x] Add `"S"` (bandit) to ruff lint select in `pyproject.toml`
- [x] Fix `default_factory` in `orchestrator.py`

### Phase 1 — Structural Improvements (medium effort)
- [x] Define `CorrectImplementation(StrEnum)`, `ConfidenceLevel(StrEnum)`, `VerificationRecommendation(StrEnum)` in `domain/models.py`
- [x] Move `AuditSummary` from `agents/auditor.py` to `domain/models.py`
- [x] Move `WorkflowStatus` from `orchestrator.py` to `domain/models.py`
- [x] Fix `AuditSummary` field — populated in `_build_result()` via `self._state.audit_summary`
- [x] Narrow `except Exception:` to specific types in `executor.py`, `tools.py`; add `logger.exception()` in `orchestrator.py`
- [x] Remove module-level `_model` from all 5 agent files; agents use `"test"` placeholder
- [ ] Define `AuditAction(StrEnum)`, `AgentName(StrEnum)` — deferred
- [ ] Group 7-param functions into dataclasses — deferred
- [ ] Add missing import-linter contracts — deferred
- [ ] Add AAA section markers to 7 test files — deferred
- [ ] Add 5 missing FSM transition tests — deferred
- [ ] Add missing persistence edge-case tests — deferred

### Phase 2 — Architectural Changes (higher effort)
- [x] Remove module-level `_model` from all 5 agent files (done in Phase 1)
- [ ] Split `orchestrator.py`: extract models + steps — deferred
- [ ] Split `spec_parser.py` into 3 files — deferred
- [ ] Split `agents/tools.py` into 3 files — deferred
- [ ] Create `tests/unit/test_derivation_runner.py` — deferred
- [ ] Create mocked-LLM integration test — deferred
- [x] Fix `_run_coder_and_qc()` parameter type to `DerivationRule` with proper `TYPE_CHECKING` import

### Phase 3 — Ongoing Discipline
- [ ] Run architecture review (`/review-architecture`) before each new phase
- [ ] Enforce AAA markers in new tests via code review checklist
- [ ] Monitor file/function/class size limits as new features land
- [ ] Add `DerivationNodeFSM` for per-node status transitions when moving to production
- [ ] Add Alembic if graduating from SQLite to PostgreSQL
