# Phase 17.2 — Per-Variable Audit Emission Inside derivation_runner (Bug #1)

**Bug:** BUGS.md #1 — `derive_variables` step audit row shows `Agent: orchestrator` and the Variable column is empty. Per-variable agent provenance (coder/QC/debugger) is not visible in the audit trail at all.

**Goal:** Emit per-variable audit events from inside `derivation_runner.run_variable` so the audit trail shows **who** (coder/QC/debugger) proposed **what** code for **which** variable, with a populated `variable` column for each event.

**Agent:** `python-fastapi`
**Depends on:** Nothing (independent of 17.1 and 17.3)
**Estimated effort:** 30–60 min
**Reference (read first):** BUGS.md §#1, `src/engine/derivation_runner.py` (the function being modified), `src/engine/step_executors.py::ParallelMapStepExecutor` (the caller — lines 197-256), `src/domain/models.py::AuditAction` (where new enum values go), `src/audit/trail.py` (the AuditTrail.record signature)

---

## Files to modify — 4 modified

### `src/domain/models.py` (MODIFY)
**Change:** Add 3 new `AuditAction` enum values for per-variable agent provenance.
**Exact change:**
1. Find `class AuditAction(StrEnum)` (or `class AuditAction(str, Enum)` — match the existing style)
2. Add three new members **after** the existing per-variable members but before any workflow-level ones:
   ```python
   CODER_PROPOSED = "coder_proposed"
   QC_VERDICT = "qc_verdict"
   DEBUGGER_RESOLVED = "debugger_resolved"
   ```
**Constraints:**
- StrEnum value strings MUST be lowercase snake_case (matches existing convention)
- Don't reorder existing members (changing position of enum members is risk-free for StrEnum but still a bad habit)
- If there's a `__all__` or re-export list, add the 3 new names

---

### `src/engine/derivation_runner.py` (MODIFY — primary change site)
**Change:** Inside `run_variable` (or wherever the coder/QC/debugger sub-agents are invoked), emit a `ctx.audit_trail.record(...)` call AFTER each sub-agent produces its output, populating the `variable` column with the variable name.
**Exact changes (per sub-agent invocation):**

1. **After the coder agent returns its result**, add:
   ```python
   ctx.audit_trail.record(
       variable=variable,
       action=AuditAction.CODER_PROPOSED,
       agent=AgentName.CODER,
       details={
           "approach": coder_result.approach,
           "code_preview": coder_result.python_code[:200],
       },
   )
   ```

2. **After the QC agent returns its result**, add:
   ```python
   ctx.audit_trail.record(
       variable=variable,
       action=AuditAction.QC_VERDICT,
       agent=AgentName.QC,
       details={
           "verdict": qc_verdict.value,  # "match" or "mismatch"
           "approach": qc_result.approach,
           "code_preview": qc_result.python_code[:200],
       },
   )
   ```

3. **After the debugger resolves a mismatch** (only on the mismatch branch), add:
   ```python
   ctx.audit_trail.record(
       variable=variable,
       action=AuditAction.DEBUGGER_RESOLVED,
       agent=AgentName.DEBUGGER,
       details={
           "root_cause": debugger_result.root_cause,
           "chose": debugger_result.correct_implementation,  # "coder" | "qc" | "neither"
           "confidence": debugger_result.confidence,
       },
   )
   ```

**IMPORTANT — caller signature change:** `run_variable` currently does NOT accept `audit_trail` as a parameter (verify this by reading the current signature — it likely receives only `dag`, `derived_df`, etc.). To call `ctx.audit_trail.record(...)` from inside, the function needs access to either the trail OR the full `ctx`. Two options:
- **Option A (preferred):** add `audit_trail: AuditTrail` parameter to `run_variable`, pass it from the ParallelMapStepExecutor call site (`audit_trail=ctx.audit_trail`)
- **Option B (less invasive):** add an optional `audit_trail: AuditTrail | None = None` parameter and gate each `record(...)` call on `if audit_trail is not None`

Use **Option A** — strict typing, no Optional, callers always pass the trail.

**Imports to add:**
```python
from src.domain.models import AuditAction, AgentName  # if not already imported
```

**Constraints:**
- Code previews truncated to 200 chars (matches the existing `slice(0, 80)` cap in `VariableApprovalList.tsx` — 200 gives audit a bit more context than UI snippets, since auditors may want to see the full expression)
- All 3 audit events use the variable name (NOT the empty string) — that's the whole point of the bug fix
- Function MUST stay under 30 lines per the project rule. If `run_variable` grows past 30 lines after these changes, extract a helper `_record_variable_event(ctx, variable, action, agent, details)`
- No `print()` debugging — use loguru `logger.debug` if needed

---

### `src/engine/step_executors.py` (MODIFY)
**Change:** Update `ParallelMapStepExecutor.execute` to pass `audit_trail=ctx.audit_trail` into `run_variable` (matches the new signature from derivation_runner).
**Exact change:**
1. Find the call to `run_variable(...)` inside `ParallelMapStepExecutor.execute` (currently at line 233-244)
2. Add `audit_trail=ctx.audit_trail,` to the kwargs (place it after `pattern_repo=ctx.pattern_repo` for consistency with the existing pattern)
**Constraints:** No other changes to this file (the step-level `step_started`/`step_completed` events stay as-is — they're correct at their granularity per BUGS.md #1).

---

### `tests/unit/test_derivation_runner.py` (MODIFY — or CREATE if doesn't exist)
**Change:** Add 2 new test cases that verify per-variable audit events fire correctly.
**Tests to add:**

1. **`test_run_variable_emits_coder_proposed_and_qc_verdict_events_on_match`**
   - **Arrange:** mock the coder agent to return a fixed result, mock the QC agent to return a matching result, build an `AuditTrail` instance, call `run_variable(..., audit_trail=trail)`
   - **Act:** run to completion
   - **Assert:** `trail` contains exactly 1 `CODER_PROPOSED` event and 1 `QC_VERDICT` event, both with `variable=<test_var_name>` populated, and 0 `DEBUGGER_RESOLVED` events (no mismatch)
   - **Use AAA markers**: `# Arrange`, `# Act`, `# Assert`

2. **`test_run_variable_emits_debugger_resolved_event_when_qc_mismatches`**
   - **Arrange:** mock the coder + QC to return divergent results, mock the debugger to return `correct_implementation="qc"`
   - **Act:** run to completion
   - **Assert:** `trail` contains 1 each of `CODER_PROPOSED`, `QC_VERDICT`, `DEBUGGER_RESOLVED`, with the debugger event's `details["chose"] == "qc"`

**Mocking strategy:**
- Mock the agent calls at the LLM gateway boundary using PydanticAI's `TestModel` or `FunctionModel` — DO NOT mock domain logic
- If `tests/unit/test_derivation_runner.py` doesn't exist, create it. Place it in `tests/unit/` next to `test_step_executors.py`.
- Use the existing `_make_ctx` or `_make_dag` helper patterns from `test_step_executors.py` if they exist

**Constraints:**
- Test names follow `test_<action>_<scenario>_<expected>`
- Use `asyncio_mode = "auto"` (no `@pytest.mark.asyncio`)
- AAA markers in every test body
- Never `pytest.raises(Exception)` — use specific exception types

---

## Files to verify but NOT modify

- `src/audit/trail.py` — verify `AuditTrail.record(variable: str, action: AuditAction, agent: AgentName, details: dict)` signature exists. If the `variable` parameter is currently typed as `str | None` or has a different name, adapt the new `record(...)` calls accordingly.
- `src/api/routers/workflows.py` — verify the `/audit` endpoint serializes the `variable` field for every event. The frontend Audit tab should automatically pick it up since it's already rendering the column.
- `frontend/src/pages/WorkflowDetailPage.tsx` (Audit tab) — should require ZERO frontend changes if the column already exists in the table. The new events will populate it automatically once the backend emits them.

---

## Implementation order (within Phase 17.2)

1. Add 3 new `AuditAction` enum values in `src/domain/models.py`
2. Update `run_variable` signature in `src/engine/derivation_runner.py` to accept `audit_trail`
3. Add the 3 `record(...)` calls inside `run_variable` (coder, QC, optionally debugger)
4. Update `ParallelMapStepExecutor.execute` to pass `audit_trail=ctx.audit_trail` into `run_variable`
5. Add the 2 new unit tests in `tests/unit/test_derivation_runner.py`

---

## Tooling gate (mandatory after Phase 17.2)

```bash
cd C:\Projects\Interviews\jobs\Sanofi-AI-ML-Lead\homework
uv run pyright .
uv run ruff check . --fix
uv run ruff format .
uv run lint-imports
uv run pytest tests/ -q
```

Special attention:
- `check_function_size` (if exists) — `run_variable` must stay ≤ 30 lines after the change. Extract a helper if needed.
- `pyright` strict mode — the new function parameter must be fully typed

---

## Acceptance criteria for Phase 17.2

- ✅ `AuditAction` enum has `CODER_PROPOSED`, `QC_VERDICT`, `DEBUGGER_RESOLVED` values
- ✅ `run_variable` signature accepts `audit_trail: AuditTrail`
- ✅ `run_variable` emits exactly 2 audit events on QC-match path (coder + qc)
- ✅ `run_variable` emits exactly 3 audit events on QC-mismatch path (coder + qc + debugger)
- ✅ Every new event has `variable=<actual_name>` populated (NOT empty string)
- ✅ Every new event has the correct `agent` value (`AgentName.CODER`, `AgentName.QC`, `AgentName.DEBUGGER`)
- ✅ `ParallelMapStepExecutor` passes `audit_trail=ctx.audit_trail` into `run_variable`
- ✅ 2+ new unit tests in `tests/unit/test_derivation_runner.py` (one per audit path)
- ✅ Total backend test count increases by 2
- ✅ All 18 pre-push hooks green
- ✅ Manual smoke test: re-run TEST_PLAN_P16.md Test 2 against the post-Phase-17.2 build → audit trail UI now shows per-variable rows for AGE_GROUP, TREATMENT_DURATION, IS_ELDERLY, RISK_SCORE with the Variable column populated and Agent column showing `coder`/`qc`/`debugger`

**This phase closes Bug #1.**
