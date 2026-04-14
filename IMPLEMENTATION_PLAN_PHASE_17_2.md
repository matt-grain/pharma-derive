# Phase 17.2 — Per-Variable Audit Emission Inside derivation_runner (Bug #1)

**Bug:** BUGS.md #1 — `derive_variables` step audit row shows `Agent: orchestrator` and the Variable column is empty. Per-variable agent provenance (coder/QC/debugger) is not visible in the audit trail at all.

**Goal:** Emit per-variable audit events from inside `derivation_runner.run_variable` so the audit trail shows **who** (coder/QC/debugger) proposed **what** code for **which** variable, with a populated `variable` column for each event.

**Agent:** `python-fastapi`
**Depends on:** Nothing (independent of 17.1 and 17.3)
**Estimated effort:** 30–60 min
**Reference (read first):** BUGS.md §#1, `src/engine/derivation_runner.py` (the function being modified), `src/engine/debug_runner.py` (where the debugger event is emitted from), `src/engine/step_executors.py::ParallelMapStepExecutor` (the caller — lines 197-256), `src/domain/enums.py::AuditAction` at line 78 + `src/domain/enums.py::AgentName` at line 94 (where new enum values go — NOT in `models.py` which only re-exports them), `src/audit/trail.py` (the AuditTrail.record signature)

---

## Files to modify — 5 modified

### `src/domain/enums.py` (MODIFY)
**Change:** Add 3 new `AuditAction` enum values for per-variable agent provenance.
**IMPORTANT — file location correction:** `AuditAction` and `AgentName` are defined in **`src/domain/enums.py`** (lines 78 and 94 respectively), NOT in `src/domain/models.py`. `models.py` only re-exports them via `from src.domain.enums import (AgentName, AuditAction, ...)` at lines 9-19. **The actual class definitions to modify are in `enums.py`.**
**Exact change:**
1. Open `src/domain/enums.py`
2. Find `class AuditAction(StrEnum):` at line 78. The existing members are: `SPEC_PARSED, DERIVATION_COMPLETE, AUDIT_COMPLETE, STATE_TRANSITION, HUMAN_APPROVED, HUMAN_OVERRIDE, HUMAN_REJECTED, STEP_STARTED, STEP_COMPLETED, HITL_GATE_WAITING, WORKFLOW_FAILED`
3. Add three new members at the END of the enum (preserve existing order):
   ```python
   CODER_PROPOSED = "coder_proposed"
   QC_VERDICT = "qc_verdict"
   DEBUGGER_RESOLVED = "debugger_resolved"
   ```
**No re-export change needed** — `src/domain/models.py:9-19` already imports `AuditAction` from `enums`, so existing callers continue to work via the re-export. New callers can import from either location.
**Constraints:**
- StrEnum value strings MUST be lowercase snake_case (matches existing convention)
- Don't reorder existing members (changing position of StrEnum members is risk-free for value-based comparison but still a bad habit)

---

### `src/engine/derivation_runner.py` (MODIFY — primary change site for coder + QC events)
**Change:** Inside `run_variable`, emit `ctx.audit_trail.record(...)` calls for the **coder** and **QC** events (not debugger — see `debug_runner.py` modify spec below for that one). The coder + QC results are returned from `_run_coder_and_qc(...)` at line 50-52, and the QC verdict is computed at line 59 by `verify_derivation`. Both events fire from inside `run_variable`.

**IMPORTANT — verified state of `src/engine/derivation_runner.py:36-65` before this fix:**
- `run_variable` signature accepts: `variable, dag, derived_df, synthetic_csv, llm_base_url, coder_agent_name, qc_agent_name, debugger_agent_name, pattern_repo` (line 36-46) — does NOT accept `audit_trail`
- Coder + QC results returned from `_run_coder_and_qc` helper (line 50-52). On line 50: `coder, qc_code = await _run_coder_and_qc(...)`
- QC verdict computed at line 59: `vr = verify_derivation(variable, coder.python_code, qc_code.python_code, derived_df, available)`
- On QC match path: `_approve_match(...)` is called (line 61)
- On QC mismatch path: `handle_mismatch(...)` is called (line 65) — debugger runs inside this helper, in `src/engine/debug_runner.py`

**Exact changes:**

1. **Add `audit_trail: AuditTrail` parameter** to `run_variable` (around line 36-46). Place it after `pattern_repo: PatternRepository | None = None` and the other 2 new repo params (`feedback_repo`, `qc_history_repo`) from Phase 17.1. Default it to a sentinel `None` ONLY for backwards compat with any legacy direct-callers — the production path will always pass it. If pyright strict objects, use a `Required` parameter without default.

2. **After line 50** (`coder, qc_code = await _run_coder_and_qc(...)`), add the CODER_PROPOSED audit event:
   ```python
   if audit_trail is not None:
       audit_trail.record(
           variable=variable,
           action=AuditAction.CODER_PROPOSED,
           agent=AgentName.CODER,
           details={
               "approach": coder.approach,
               "code_preview": coder.python_code[:200],
           },
       )
   ```

3. **After line 50 BUT BEFORE the express-mode `if qc_code is None:` branch on line 54**, add the CODER event but ONLY emit the QC event if `qc_code is not None`. The cleanest pattern: emit CODER, then check `if qc_code is not None` and emit QC. Looking at existing code, the order is: get coder+qc, check express mode (if qc_code is None return), then verify. The QC event should fire AFTER `vr = verify_derivation(...)` on line 59 so we have the verdict.

4. **After line 59** (`vr = verify_derivation(...)`), add the QC_VERDICT audit event:
   ```python
   if audit_trail is not None:
       audit_trail.record(
           variable=variable,
           action=AuditAction.QC_VERDICT,
           agent=AgentName.QC_PROGRAMMER,
           details={
               "verdict": vr.verdict.value,  # "match" or "mismatch"
               "approach": qc_code.approach,
               "code_preview": qc_code.python_code[:200],
           },
       )
   ```

5. **Update the call to `handle_mismatch` on line 65** to pass `audit_trail` through:
   ```python
   await handle_mismatch(variable, dag, derived_df, coder, qc_code, vr, llm_base_url, debugger_name, audit_trail=audit_trail)
   ```
   (Adding `audit_trail` as a kwarg.)

**Imports to add at the top of `src/engine/derivation_runner.py`:**
```python
from src.domain.enums import AgentName, AuditAction  # NEW — for the audit events
```
And under `TYPE_CHECKING`:
```python
from src.audit.trail import AuditTrail
```

**Constraints:**
- Code previews truncated to 200 chars (matches the existing `slice(0, 80)` cap in `VariableApprovalList.tsx` — 200 gives audit a bit more context than UI snippets, since auditors may want to see the full expression)
- All audit events use the variable name (NOT the empty string) — that's the whole point of the bug fix
- Function MUST stay under 30 lines per the project rule. **`run_variable` is currently at ~32 lines** — adding 2 audit blocks will push it over. **Extract a helper** `_record_coder_qc_audit(audit_trail, variable, coder, qc_code, vr)` that emits both events, and call it from `run_variable` to keep the function body lean.
- No `print()` debugging — use loguru `logger.debug` if needed

---

### `src/engine/debug_runner.py` (MODIFY — DEBUGGER_RESOLVED event lives here)
**Change:** Emit the `DEBUGGER_RESOLVED` audit event from inside `handle_mismatch` (the function that owns the debugger invocation). The debugger result is `analysis: DebugAnalysis`, which has fields `root_cause: str`, `correct_implementation: CorrectImplementation` (an enum with values `CODER | QC | NEITHER`), and `suggested_fix: str | None`.

**IMPORTANT — verified state of `src/engine/debug_runner.py` before this fix:**
- `handle_mismatch` signature at line 158-167: takes `variable, dag, derived_df, coder, qc_code, vr, llm_base_url, debugger_agent_name`. Does NOT take `audit_trail`.
- `analysis = await _debug_variable(ctx, dag, derived_df, vr)` at line 176 — this is where the debugger result becomes available
- `analysis.correct_implementation` is a `CorrectImplementation` enum (verify members in `src/domain/enums.py`)

**Exact changes:**

1. **Add `audit_trail: AuditTrail | None = None`** as the last keyword parameter of `handle_mismatch`. Default to `None` so existing tests that call it directly without an audit trail keep working.

2. **After line 176** (`analysis = await _debug_variable(ctx, dag, derived_df, vr)`), add the DEBUGGER_RESOLVED audit event:
   ```python
   if audit_trail is not None:
       audit_trail.record(
           variable=variable,
           action=AuditAction.DEBUGGER_RESOLVED,
           agent=AgentName.DEBUGGER,
           details={
               "root_cause": analysis.root_cause,
               "chose": analysis.correct_implementation.value,  # CorrectImplementation.value: "coder" | "qc" | "neither"
               "suggested_fix_present": analysis.suggested_fix is not None and bool(analysis.suggested_fix.strip()),
           },
       )
   ```

**Imports to add at the top of `src/engine/debug_runner.py`:**
```python
from src.domain.enums import AgentName, AuditAction  # NEW
```
And under `TYPE_CHECKING`:
```python
from src.audit.trail import AuditTrail
```

**Constraints:**
- The event MUST fire AFTER the debugger returns its analysis, regardless of whether the fix succeeds (the audit trail captures the debugger's reasoning, not whether the fix worked)
- Use `analysis.correct_implementation.value` (not `.name`) — `CorrectImplementation` is a StrEnum, the `.value` is the lowercase string
- Function MUST stay under 30 lines per the project rule. `handle_mismatch` is currently ~25 lines; adding this block keeps it under 30.

---

### `src/engine/step_executors.py` (MODIFY)
**Change:** Update `ParallelMapStepExecutor.execute` to pass `audit_trail=ctx.audit_trail` into `run_variable` (matches the new signature from derivation_runner).
**Exact change:**
1. Find the call to `run_variable(...)` inside `ParallelMapStepExecutor.execute` (currently at line 233-244)
2. Add `audit_trail=ctx.audit_trail,` to the kwargs (place it after `pattern_repo=ctx.pattern_repo` for consistency with the existing pattern)
**Constraints:** No other changes to this file (the step-level `step_started`/`step_completed` events stay as-is — they're correct at their granularity per BUGS.md #1).

---

### `tests/unit/test_derivation_runner.py` (MODIFY — file already exists, confirmed)
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

1. Add 3 new `AuditAction` enum values in **`src/domain/enums.py`** (NOT `models.py` — verified location: `enums.py:78`)
2. Update `run_variable` signature in `src/engine/derivation_runner.py` to accept `audit_trail: AuditTrail | None = None`
3. Add the 2 audit `record(...)` calls inside `run_variable` (CODER_PROPOSED + QC_VERDICT). Extract a helper to keep `run_variable` under 30 lines.
4. Add `audit_trail` parameter to `handle_mismatch` in `src/engine/debug_runner.py` and emit the DEBUGGER_RESOLVED event after `_debug_variable` returns
5. Update `run_variable`'s call to `handle_mismatch` to pass `audit_trail` through
6. Update `ParallelMapStepExecutor.execute` in `src/engine/step_executors.py` to pass `audit_trail=ctx.audit_trail` into `run_variable`
7. Add the 2 new unit tests in `tests/unit/test_derivation_runner.py` (both happy-path tests verify `audit_trail.records` after the run)

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
- ✅ Every new event has the correct `agent` value (`AgentName.CODER`, `AgentName.QC_PROGRAMMER`, `AgentName.DEBUGGER`)
- ✅ `ParallelMapStepExecutor` passes `audit_trail=ctx.audit_trail` into `run_variable`
- ✅ 2+ new unit tests in `tests/unit/test_derivation_runner.py` (one per audit path)
- ✅ Total backend test count increases by 2
- ✅ All 18 pre-push hooks green
- ✅ Manual smoke test: re-run TEST_PLAN_P16.md Test 2 against the post-Phase-17.2 build → audit trail UI now shows per-variable rows for AGE_GROUP, TREATMENT_DURATION, IS_ELDERLY, RISK_SCORE with the Variable column populated and Agent column showing `coder`/`qc`/`debugger`

**This phase closes Bug #1.**
