# Phase 6 — Review Fix: Deferred Items

**Dependencies:** Phases 1-4 (complete). Independent of Phase 5.
**Agent:** `general-purpose`
**Estimated files:** ~18

This phase addresses ALL 15 deferred items from the architecture review (REVIEW.md). Grouped into 4 sub-phases for manageability.

---

## 6A — File Splits (orchestrator, spec_parser, tools)

### 6A.1 Split `src/engine/orchestrator.py` (243 lines → ~150 + ~90)

**Extract:** `src/engine/workflow_models.py` (NEW)

**Move from orchestrator.py to workflow_models.py:**
- `WorkflowState` dataclass (lines 40-53)
- `WorkflowResult` Pydantic model (lines 56-66)
- All imports needed by these two classes

**After split:**
- `orchestrator.py` keeps `DerivationOrchestrator` class + `run()` + step methods
- `orchestrator.py` imports `WorkflowState, WorkflowResult` from `workflow_models`
- Target: orchestrator.py < 200 lines, workflow_models.py < 100 lines

**Update imports in:** `tests/unit/test_orchestrator.py`, `tests/integration/test_workflow.py` — both import `WorkflowState` or `WorkflowResult`

### 6A.2 Split `src/domain/spec_parser.py` (164 lines → 3 files)

**NOTE:** If Phase 5 has already been implemented, `spec_parser.py` will contain XPT loading code (pyreadstat import + xpt branch in `load_source_data()`). The XPT code moves into `source_loader.py` along with the rest of `load_source_data()`. If Phase 5 has NOT been implemented yet, `source_loader.py` will only contain CSV loading — the XPT code is added when Phase 5 runs.

**Create:** `src/domain/source_loader.py` (NEW)
- Move: `load_source_data()`, `get_source_columns()`
- Imports: `Path`, `pd`, `pyreadstat` (if Phase 5 is done), `TransformationSpec`

**Create:** `src/domain/synthetic.py` (NEW)
- Move: `generate_synthetic()`, `_is_date_column()`, `_random_date_between()`
- Imports: `date`, `timedelta`, `np`, `pd`, `re`, `_DATE_PATTERN`

**Keep in `spec_parser.py`:** `parse_spec()` only (~70 lines)

**Update imports in:**
- `src/engine/orchestrator.py` — currently `from src.domain.spec_parser import generate_synthetic, get_source_columns, load_source_data, parse_spec` → split into two imports
- `tests/unit/test_spec_parser.py` — update any direct imports

**Re-export from `src/domain/__init__.py`** if needed for ergonomic imports.

### 6A.3 Split `src/agents/tools.py` (191 lines → 2 files)

**Create:** `src/agents/deps.py` (NEW)
- Move: `CoderDeps` dataclass (~10 lines)
- Imports: `dataclass`, `pd`, `TYPE_CHECKING` for `DerivationRule`

**Keep in `tools.py`:** All tool functions and helpers (~180 lines — still under 200)

**Update imports in:**
- `src/engine/derivation_runner.py` — `from src.agents.tools import CoderDeps` → `from src.agents.deps import CoderDeps`
- `tests/unit/test_agent_tools.py` — if it imports `CoderDeps`

---

## 6B — Missing Enums

### 6B.1 Define `AuditAction` and `AgentName` enums

**File:** `src/domain/models.py` (MODIFY)

**Add after `VerificationRecommendation`:**

```python
class AuditAction(StrEnum):
    """Actions recorded in the audit trail."""
    SPEC_PARSED = "spec_parsed"
    DERIVATION_COMPLETE = "derivation_complete"
    AUDIT_COMPLETE = "audit_complete"
    STATE_TRANSITION = "state_transition"


class AgentName(StrEnum):
    """Agent identifiers used in audit records."""
    ORCHESTRATOR = "orchestrator"
    CODER = "coder"
    QC_PROGRAMMER = "qc_programmer"
    DEBUGGER = "debugger"
    AUDITOR = "auditor"
```

**Update consumers:**
- `src/engine/orchestrator.py` — replace `action="spec_parsed"` with `AuditAction.SPEC_PARSED`, `agent="orchestrator"` with `AgentName.ORCHESTRATOR`, etc. (4 call sites)
- `src/engine/workflow_fsm.py` — replace `agent="orchestrator"` with `AgentName.ORCHESTRATOR` (1 call site); replace `action=f"state_transition:{target.id}"` with an f-string using `AuditAction.STATE_TRANSITION`
- Add imports to both files

### 6B.2 Group 7-param functions into dataclasses

**File:** `src/engine/derivation_runner.py` (MODIFY) — NOT in `domain/models.py` (domain must not import agents-layer types like `DerivationCode`)

Add at module level (after imports):
```python
@dataclass
class DebugContext:
    """Context for the debug loop — groups params to keep _debug_variable under 5 args."""
    variable: str
    coder: DerivationCode
    qc_code: DerivationCode
    llm_base_url: str
```

Change signature:
```python
# Before (7 params):
async def _debug_variable(variable, dag, derived_df, vr, coder, qc_code, llm_base_url) -> DebugAnalysis:

# After (4 params):
async def _debug_variable(ctx: DebugContext, dag: DerivationDAG, derived_df: pd.DataFrame, vr: VerificationResult) -> DebugAnalysis:
```

Update the call site in `run_variable()`:
```python
ctx = DebugContext(variable=variable, coder=coder, qc_code=qc_code, llm_base_url=llm_base_url)
analysis = await _debug_variable(ctx, dag, derived_df, vr)
```

**File:** `src/verification/comparator.py` — **NO CHANGE.** `verify_derivation()` has 7 params but 2 (`tolerance`, `independence_threshold`) have defaults. Effective required params = 5. This is at the limit, not over it. Keep as-is — add a `# 5 required + 2 with defaults = acceptable` comment above the function.

---

## 6C — Missing Import-Linter Contracts

### `.importlinter` (MODIFY)

**Add these contracts:**

```ini
[importlinter:contract:audit-no-agents]
name = Audit cannot import from Agents
type = forbidden
source_modules = src.audit
forbidden_modules = src.agents

[importlinter:contract:ui-no-persistence]
name = UI cannot import Persistence directly
type = forbidden
source_modules = src.ui
forbidden_modules = src.persistence
```

Note: `ui-no-persistence` is proactive — enforced when `src/ui/` is created in Phase 7. UI can import domain models (for display) and engine (for orchestrator), but NOT persistence directly (DB access goes through engine).

---

## 6D — Missing Tests + Test Quality

### 6D.1 `tests/unit/test_derivation_runner.py` (NEW)

**Purpose:** Test the core per-variable execution engine.

**Tests to write (mock all agents via `pydantic_ai.models.test.TestModel`):**

- `test_run_variable_match_approves_and_adds_column` — happy path: coder+QC produce matching code, variable is approved, column added to derived_df
- `test_run_variable_mismatch_triggers_debug` — QC mismatch triggers debugger agent call
- `test_run_variable_debug_fix_applied` — debugger recommends coder's code, it gets applied
- `test_run_variable_debug_neither_sets_qc_mismatch` — debugger says "neither", status = QC_MISMATCH
- `test_resolve_approved_code_suggested_fix_preferred` — suggested_fix takes priority over coder/qc
- `test_resolve_approved_code_coder_selected` — correct_implementation=CODER returns coder code
- `test_resolve_approved_code_qc_selected` — correct_implementation=QC returns qc code
- `test_resolve_approved_code_neither_returns_none` — correct_implementation=NEITHER returns None
- `test_apply_approved_adds_column_to_df` — verify column is added to derived_df
- `test_apply_debug_fix_success_approves` — execute_derivation succeeds, node approved
- `test_apply_debug_fix_failure_marks_mismatch` — execute_derivation fails, node = QC_MISMATCH

**Mocking strategy:**
- Use `pydantic_ai.models.test.TestModel` with `custom_output_args` for each agent
- Mock `verify_derivation` to return controlled `VerificationResult`
- Use `sample_df` and `sample_rules` fixtures from conftest

**Constraints:**
- Follow AAA pattern with `# Arrange`, `# Act`, `# Assert` markers
- Test names follow `test_<action>_<scenario>_<expected>`
- No real LLM calls

### 6D.2 `tests/unit/test_logging.py` (NEW)

**Purpose:** Test `setup_logging()`.

**Tests:**
- `test_setup_logging_default_runs_without_error` — call with no args, no exception
- `test_setup_logging_with_file_creates_sink` — pass a `tmp_path` log file, verify no error
- `test_setup_logging_custom_level` — pass `level="DEBUG"`, verify no error

### 6D.3 Missing FSM Transition Tests

**File:** `tests/unit/test_workflow_fsm.py` (MODIFY)

**Add 6 tests:**
- `test_fsm_fail_from_dag_built_transitions_to_failed`
- `test_fsm_fail_from_debugging_transitions_to_failed`
- `test_fsm_fail_from_review_transitions_to_failed`
- `test_fsm_fail_from_auditing_transitions_to_failed`
- `test_fsm_finish_review_from_debug_transitions_to_review`
- `test_fsm_fail_method_from_any_non_terminal_state` — parametrized test using `fail()` helper

**Pattern:** Follow existing tests in the file. Each test creates a `WorkflowFSM`, transitions to the source state, then calls the fail transition, and asserts `fsm.current_state_value == "failed"`.

### 6D.4 Missing Persistence Edge-Case Tests

**File:** `tests/unit/test_persistence.py` (MODIFY)

**Add 3 tests:**
- `test_feedback_repo_query_empty_returns_empty_list` — no records → `[]`
- `test_feedback_repo_query_respects_limit` — store 5 records, query limit=2 → 2 results
- `test_qc_repo_stats_filtered_by_variable` — store records for 2 variables, query with `variable="AGE_GROUP"` → only AGE_GROUP counts

### 6D.5 AAA Markers in Test Files

**Files to modify (add `# Arrange`, `# Act`, `# Assert` comments):**
- `tests/unit/test_dag.py`
- `tests/unit/test_models.py`
- `tests/unit/test_workflow_fsm.py`
- `tests/unit/test_comparator.py`
- `tests/unit/test_executor.py`
- `tests/unit/test_spec_parser.py`
- `tests/unit/test_agent_config.py`
- `tests/unit/test_orchestrator.py`
- `tests/unit/test_agent_tools.py`

**Rule:** Add `# Arrange`, `# Act`, `# Assert` section markers to every test body. For trivial 1-2 line tests, use `# Act & Assert`.

---

## Implementation Order within Phase 6

```
6A (file splits) → 6B (enums) → 6C (linter contracts) → 6D (tests)
```

6A must go first because 6B-6D reference the new file paths. 6D tests validate everything.
