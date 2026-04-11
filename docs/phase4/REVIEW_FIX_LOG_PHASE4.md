# Fix Log — pharma-derive

**Date:** 2026-04-09
**Based on:** REVIEW.md dated 2026-04-09

## Summary

| Phase | Fix Units | Fully Fixed | Partial | Files Modified |
|-------|-----------|-------------|---------|----------------|
| Phase 0 | 8 | 8 | 0 | 11 |
| Phase 1 | 3 | 3 | 0 | 11 |
| Phase 2 | 3 | 3 | 0 | 3 |
| **Total** | **14** | **14** | **0** | **~20 unique** |

## Fix Details

### Fix Unit 1: Add `from __future__ import annotations` to models.py
- **Files modified:** `src/domain/models.py`
- **Verification:** ✅ Import present

### Fix Unit 2: Replace raw string enum comparisons
- **Files modified:** `src/engine/derivation_runner.py`, `src/persistence/repositories.py`, `src/engine/orchestrator.py`
- **Verification:** ✅ Grep `== "match"`, `== "completed"`, `== "pending"` returns 0 matches in src/

### Fix Unit 3: Add `Final[...]` to module constants
- **Files modified:** `src/engine/llm_gateway.py`, `src/agents/tools.py`, `src/domain/spec_parser.py`
- **Verification:** ✅ All constants annotated with `Final`

### Fix Unit 4: Fix `default_factory=lambda: []`
- **Files modified:** `src/engine/orchestrator.py`
- **Verification:** ✅ Uses `lambda: list[str]()` (pyright-compatible)

### Fix Unit 5: Remove redundant `@pytest.mark.asyncio`
- **Files modified:** `tests/unit/test_agent_tools.py`
- **Verification:** ✅ Grep returns 0 matches

### Fix Unit 6: Replace `pytest.raises(Exception)` with specific types
- **Files modified:** `tests/unit/test_spec_parser.py`, `tests/integration/test_workflow.py`
- **Verification:** ✅ Grep returns 0 matches

### Fix Unit 7: Move local imports to top-level
- **Files modified:** `src/engine/derivation_runner.py`
- **Verification:** ✅ `DerivationRule` in TYPE_CHECKING block, `execute_derivation` at top-level, `rule: DerivationRule` properly typed

### Fix Unit 8: Add ruff `"S"` security ruleset
- **Files modified:** `pyproject.toml`, `src/domain/executor.py`, `src/agents/tools.py`
- **Verification:** ✅ `"S"` in ruff select, `# noqa: S307` on eval, `# noqa: S102` on exec, per-file-ignores for S101

### Fix Unit 9: Define missing StrEnums + update consumers
- **Files modified:** `src/domain/models.py`, `src/agents/debugger.py`, `src/verification/comparator.py`, `src/engine/derivation_runner.py`, `src/persistence/repositories.py`, `tests/unit/test_persistence.py`
- **Verification:** ✅ Grep for raw string assignments (`== "coder"`, `recommendation="needs_debug"`, `verdict: str`) returns 0 matches

### Fix Unit 10: Move AuditSummary to domain + fix dead field + consolidate WorkflowStatus
- **Files modified:** `src/domain/models.py`, `src/agents/auditor.py`, `src/engine/orchestrator.py`, `tests/unit/test_agent_config.py`, `tests/integration/test_workflow.py`, `tests/unit/test_orchestrator.py`
- **Verification:** ✅ `AuditSummary` in domain, field populated in `_build_result()`, `WorkflowStatus` in domain, all imports updated

### Fix Unit 11: Remove module-level `_model` from all agents
- **Files modified:** `src/agents/auditor.py`, `src/agents/debugger.py`, `src/agents/derivation_coder.py`, `src/agents/qc_programmer.py`, `src/agents/spec_interpreter.py`
- **Verification:** ✅ Grep for `OpenAIChatModel` in `src/agents/` returns 0 matches

### Fix Unit 12: Narrow `except Exception` in executor.py
- **Files modified:** `src/domain/executor.py`
- **Verification:** ✅ Catches 8 specific exception types

### Fix Unit 13: Narrow `except Exception` in tools.py
- **Files modified:** `src/agents/tools.py`
- **Verification:** ✅ Catches 8 specific exception types

### Fix Unit 14: Add logging + keep broad catch in orchestrator.py
- **Files modified:** `src/engine/orchestrator.py`
- **Verification:** ✅ `logger.exception()` added before absorbing, loguru imported

## Tooling Gates

All passed after each phase:
- `uv run ruff check src/ tests/` — All checks passed
- `uv run pyright src/` — 0 errors
- `uv run lint-imports` — 17 contracts kept, 0 broken
- `uv run pytest tests/ -x -q` — 118 passed

## Remaining Issues (deferred to future phases)

**Testing gaps (highest priority for next phase):**
- `derivation_runner.py` — zero test coverage
- `logging.py` — zero test coverage
- 5 FSM transitions untested
- No mocked-LLM integration test
- FeedbackRepo/QCHistoryRepo edge cases untested

**File size / splitting (medium priority):**
- `orchestrator.py` still 238 lines (extract WorkflowState/Result to workflow_models.py)
- `spec_parser.py` mixes 3 responsibilities
- `tools.py` mixes types + implementations

**Enum discipline (lower priority):**
- `AuditRecord.action` and `.agent` still raw strings
- `WorkflowFSM.fail()` still uses f-string + getattr

## Next Steps
- Run `/plan-release` to plan phases 5+ (CDISC data, Streamlit, Docker, design doc, presentation)
- Address remaining test gaps as part of the next implementation phase
- File splitting can be done as a dedicated refactor commit before new features
