# Review Validation Report — pharma-derive

**Date:** 2026-04-09
**Review date:** 2026-04-09
**Project type:** Python (generic) — PydanticAI-based agentic system

## Validation Summary

| Category | Findings Checked | ✅ Pass | ⚠️ Partial | ❌ Fail | ⏭️ Deferred | Completion* |
|----------|-----------------|---------|------------|---------|-------------|------------|
| Architecture & SoC | 8 | 5 | 0 | 0 | 3 | 100% |
| Typing & Style | 8 | 6 | 0 | 0 | 2 | 100% |
| State & Enums | 11 | 9 | 0 | 0 | 2 | 100% |
| Testing | 9 | 2 | 0 | 0 | 7 | 100% |
| Documentation & Debt | 12 | 7 | 0 | 0 | 5 | 100% |
| Tooling Checks | 5 | 5 | 0 | 0 | 0 | 100% |
| **Migration Plan** | **26** | **16** | **0** | **0** | **10** | **100%** |
| **TOTAL** | **79** | **50** | **0** | **0** | **29** | **100%** |

*Completion % = Pass / (Pass + Partial + Fail). Deferred items excluded from denominator.

## Overall Verdict

✅ **ALL CLEAR** — Every finding that was targeted for fixing is fully resolved. All 18 critical+warning fixes verified with zero regressions. 29 items intentionally deferred and documented. All tooling gates pass (ruff, pyright, lint-imports, pytest 118/118, radon).

## Detailed Results

### 1. Architecture & Separation of Concerns

| Status | Original Finding | Scope Checked | Files Still Affected | Details |
|--------|-----------------|---------------|---------------------|---------|
| ✅ PASS | `AuditSummary` imported from agents into engine | All files | 0 | Moved to `src/domain/models.py`. All consumers import from domain. |
| ✅ PASS | `AuditSummary` field never populated | `orchestrator.py` | 0 | `self._state.audit_summary = result.output` at line 200; passed to `WorkflowResult` at line 240 |
| ✅ PASS | All 5 agents had hardcoded `OpenAIChatModel` | All `src/agents/` | 0 | Zero matches for `OpenAIChatModel`, `OpenAIProvider`, `not-needed-for-mailbox`, `localhost:8650` |
| ✅ PASS | `WorkflowStatus` duplicated in orchestrator | All files | 0 | Exists only in `src/domain/models.py` |
| ✅ PASS | Unjustified local imports in `derivation_runner.py` | `derivation_runner.py` | 0 | `DerivationRule` in TYPE_CHECKING; `execute_derivation` at top-level |
| ⏭️ DEFERRED | `orchestrator.py` exceeds 200 lines | `orchestrator.py` | 243 lines | Split planned for future phase |
| ⏭️ DEFERRED | Missing import-linter contracts | `.importlinter` | No `audit-no-agents`, no `ui-no-*` | Planned for future phase |
| ⏭️ DEFERRED | `agents/tools.py` dual purpose | `tools.py` | 191 lines | Split planned for future phase |

### 2. Typing & Style

| Status | Original Finding | Scope Checked | Files Still Affected | Details |
|--------|-----------------|---------------|---------------------|---------|
| ✅ PASS | `from __future__ import annotations` missing | All 20 non-`__init__` src files | 0 | All 20 files confirmed present |
| ✅ PASS | `except Exception` swallows without logging | `orchestrator.py` | 0 | `logger.exception()` added at line 117-118 |
| ✅ PASS | `except Exception` too broad in executor | `executor.py` | 0 | Catches 8 specific types |
| ✅ PASS | `rule: object` type hack | `derivation_runner.py` | 0 | Now `rule: DerivationRule` with TYPE_CHECKING import |
| ✅ PASS | Constants lack `Final[...]` | 3 files | 0 | All constants in `llm_gateway.py`, `tools.py`, `spec_parser.py` annotated |
| ✅ PASS | `_MAX_DEBUG_RETRIES` dead code | All src/ | 0 | Fully removed |
| ⏭️ DEFERRED | Functions with 7 params | 2 functions | Both still 7 params | Grouping into dataclasses planned |
| ⏭️ DEFERRED | Loguru only in 3 files | All src/ | 17 files lack loguru | Instrumentation expansion planned |

### 3. State Management & Enums

| Status | Original Finding | Scope Checked | Files Still Affected | Details |
|--------|-----------------|---------------|---------------------|---------|
| ✅ PASS | `correct_implementation` was `str` | `debugger.py`, `models.py` | 0 | Now `CorrectImplementation` StrEnum |
| ✅ PASS | Raw `== "coder"` / `== "qc"` | All src/ | 0 | Uses `CorrectImplementation.CODER` / `.QC` |
| ✅ PASS | `confidence` was `str` | `debugger.py`, `models.py` | 0 | Now `ConfidenceLevel` StrEnum |
| ✅ PASS | `verdict: str` in QCHistoryRepo | `repositories.py` | 0 | Now `verdict: QCVerdict`, stores `.value` |
| ✅ PASS | Raw `"match"` in `get_stats()` | All src/ | 0 | Uses `QCVerdict.MATCH.value` |
| ✅ PASS | `.value == "match"` bypassing enum | All src/ | 0 | Uses `vr.verdict == QCVerdict.MATCH` |
| ✅ PASS | `== "completed"` raw string | All src/ | 0 | Uses `WorkflowStep.COMPLETED.value` |
| ✅ PASS | Raw `"pending"` fallback | `orchestrator.py` | 0 | Uses `DerivationStatus.PENDING.value` |
| ✅ PASS | `recommendation` raw strings | `comparator.py`, `models.py` | 0 | Now `VerificationRecommendation` StrEnum |
| ⏭️ DEFERRED | `AuditRecord.action`/`.agent` raw strings | 4 call sites | Still raw strings | Planned for future phase |
| ⏭️ DEFERRED | `WorkflowFSM.fail()` f-string+getattr | `workflow_fsm.py` | Still dynamic dispatch | Planned for future phase |

### 4. Testing Quality

| Status | Original Finding | Scope Checked | Files Still Affected | Details |
|--------|-----------------|---------------|---------------------|---------|
| ⏭️ DEFERRED | `derivation_runner.py` zero test coverage | test dir | No test file exists | Planned for next phase |
| ⏭️ DEFERRED | `logging.py` no tests | test dir | No test file exists | Planned for next phase |
| ⏭️ DEFERRED | 5 FSM transitions untested | `test_workflow_fsm.py` | All 5 still missing | Planned for next phase |
| ⏭️ DEFERRED | AAA markers missing | 12 test files | 9 files still missing | 3 files have markers |
| ✅ PASS | `pytest.raises(Exception)` too broad | All test files | 0 | Zero matches |
| ⏭️ DEFERRED | `orchestrator.run()` untested | test files | No test calls `run()` | Planned for next phase |
| ⏭️ DEFERRED | Persistence edge-case tests | `test_persistence.py` | FeedbackRepo, QCHistoryRepo gaps | Planned for next phase |
| ✅ PASS | Redundant `@pytest.mark.asyncio` | All test files | 0 | Zero matches |
| ⏭️ DEFERRED | No mocked-LLM integration test | integration tests | No TestModel usage | Planned for next phase |

### 5. Documentation & Cognitive Debt

| Status | Original Finding | Scope Checked | Files Still Affected | Details |
|--------|-----------------|---------------|---------------------|---------|
| ⏭️ DEFERRED | `generate_synthetic()` 42 lines | `spec_parser.py` | Still 42 lines | Split planned |
| ⏭️ DEFERRED | `_step_audit()` 32 lines | `orchestrator.py` | Still 32 lines | Split planned |
| ⏭️ DEFERRED | `DerivationOrchestrator` 173 lines | `orchestrator.py` | Still 173 lines | Split planned |
| ⏭️ DEFERRED | `spec_parser.py` mixes 3 responsibilities | `spec_parser.py` | Still 164 lines, 3 concerns | Split planned |
| ⏭️ DEFERRED | `tools.py` mixes types + tools | `tools.py` | Still 191 lines, dual purpose | Split planned |
| ✅ PASS | Ruff `"S"` security ruleset | `pyproject.toml`, executor, tools | 0 | `"S"` in select; `noqa: S102/S307` on exec/eval; per-file-ignores for S101 |
| ✅ PASS | ARCHITECTURE.md exists with all sections | Root | 0 | All required sections present |
| ✅ PASS | decisions.md exists | Root | 0 | 7 ADRs recorded |
| ✅ PASS | uv.lock committed | Root | 0 | Present |
| ✅ PASS | No TODO/FIXME without tracker | All src/ | 0 | Zero matches |
| ✅ PASS | No f-string SQL | All src/ | 0 | Zero matches |
| ✅ PASS | No hardcoded secrets | All src/ | 0 | Zero matches |

### 6. Tooling Verification

| Tool | Status | Errors | Warnings | Key Issues |
|------|--------|--------|----------|------------|
| pyright | ✅ Pass | 0 | 0 | Clean |
| ruff check | ✅ Pass | 0 | 0 | All checks passed |
| lint-imports | ✅ Pass | 0 | 0 | 17 contracts kept, 0 broken |
| pytest | ✅ Pass | 0 | 0 | 118 passed in 5.00s |
| radon | ⚠️ Note | 0 | 1 | `generate_synthetic` complexity C (13.0) — deferred for splitting |

### 7. Migration Plan Items

| Status | Phase | Item | Details |
|--------|-------|------|---------|
| ✅ | Phase 0 | Add `from __future__ import annotations` to models.py | Done |
| ✅ | Phase 0 | Replace `vr.verdict.value == "match"` | Done |
| ✅ | Phase 0 | Replace `== "completed"` raw string | Done |
| ✅ | Phase 0 | Replace `"pending"` raw string | Done |
| ✅ | Phase 0 | Replace `"match"` in repositories | Done |
| ✅ | Phase 0 | Change `verdict: str` to `QCVerdict` | Done |
| ✅ | Phase 0 | Add `Final[...]` to constants | Done |
| ✅ | Phase 0 | Remove `_MAX_DEBUG_RETRIES` | Done |
| ✅ | Phase 0 | Remove `@pytest.mark.asyncio` | Done |
| ✅ | Phase 0 | Replace `pytest.raises(Exception)` | Done |
| ✅ | Phase 0 | Move local imports to top-level | Done |
| ✅ | Phase 0 | Add `"S"` to ruff | Done |
| ✅ | Phase 0 | Fix `default_factory` | Done |
| ✅ | Phase 1 | Define 3 new StrEnums | Done |
| ✅ | Phase 1 | Move `AuditSummary` to domain | Done |
| ✅ | Phase 1 | Move `WorkflowStatus` to domain | Done |
| ✅ | Phase 1 | Populate `AuditSummary` field | Done |
| ✅ | Phase 1 | Narrow `except Exception` + add logging | Done |
| ✅ | Phase 1 | Remove module-level `_model` from agents | Done |
| ⏭️ | Phase 1 | Define `AuditAction`, `AgentName` enums | Deferred |
| ⏭️ | Phase 1 | Group 7-param functions into dataclasses | Deferred |
| ⏭️ | Phase 1 | Add missing import-linter contracts | Deferred |
| ⏭️ | Phase 1 | Add AAA markers to test files | Deferred |
| ⏭️ | Phase 1 | Add 5 missing FSM transition tests | Deferred |
| ⏭️ | Phase 1 | Add persistence edge-case tests | Deferred |
| ⏭️ | Phase 2 | Split orchestrator.py | Deferred |
| ⏭️ | Phase 2 | Split spec_parser.py | Deferred |
| ⏭️ | Phase 2 | Split tools.py | Deferred |
| ⏭️ | Phase 2 | Create test_derivation_runner.py | Deferred |
| ⏭️ | Phase 2 | Create mocked-LLM integration test | Deferred |
| ✅ | Phase 2 | Fix `rule: object` → `DerivationRule` | Done |

### Test Coverage Matrix

| Source Module | Test File | Coverage |
|--------------|-----------|----------|
| `src/domain/dag.py` | `test_dag.py` | ✅ Covered |
| `src/domain/models.py` | `test_models.py` | ✅ Covered |
| `src/domain/spec_parser.py` | `test_spec_parser.py` | ✅ Covered |
| `src/domain/executor.py` | `test_executor.py` | ✅ Covered |
| `src/engine/workflow_fsm.py` | `test_workflow_fsm.py` | ⚠️ Partial (5 transitions missing) |
| `src/engine/orchestrator.py` | `test_orchestrator.py` + `test_workflow.py` | ⚠️ Partial (`run()` untested) |
| `src/engine/derivation_runner.py` | — | ❌ No tests |
| `src/engine/logging.py` | — | ❌ No tests |
| `src/engine/llm_gateway.py` | `test_agent_config.py` | ✅ Covered |
| `src/persistence/repositories.py` | `test_persistence.py` | ⚠️ Partial (edge cases missing) |
| `src/persistence/database.py` | `test_persistence.py` | ✅ Covered |
| `src/audit/trail.py` | `test_audit.py` | ✅ Covered |
| `src/verification/comparator.py` | `test_comparator.py` | ✅ Covered |
| `src/agents/tools.py` | `test_agent_tools.py` | ✅ Covered |
| `src/agents/*.py` (5 agents) | `test_agent_config.py` | ⚠️ Config only |

## Deferred Items (not in scope for /heal-review)

| Item | Reason for Deferral |
|------|-------------------|
| Split `orchestrator.py` (243 lines) | Planned for next implementation phase alongside new features |
| Split `spec_parser.py` (164 lines, 3 responsibilities) | Planned for next phase |
| Split `tools.py` (191 lines, dual purpose) | Planned for next phase |
| Add `AuditAction`/`AgentName` enums | Lower priority; raw strings in audit records are not a correctness issue |
| Refactor `WorkflowFSM.fail()` dynamic dispatch | Works correctly; aesthetic improvement |
| Group 7-param functions into dataclasses | Planned for next phase |
| Expand loguru to 17 more files | Planned for next phase |
| Add missing import-linter contracts | Planned for next phase |
| Create `test_derivation_runner.py` | Planned for next implementation phase |
| Create `test_logging.py` | Planned for next phase |
| Add 5 FSM transition tests | Planned for next phase |
| Add AAA markers to 9 test files | Planned for next phase |
| Add persistence edge-case tests | Planned for next phase |
| Add mocked-LLM integration test | Planned for next phase |
| `orchestrator.run()` tests | Planned for next phase |
