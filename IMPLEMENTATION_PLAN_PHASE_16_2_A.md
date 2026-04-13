# Phase 16.2a — HITL Backend Plumbing

**Agent:** `python-fastapi`
**Depends on:** Phase 16.1 (pattern_repo / qc_history_repo wired onto PipelineContext)
**Runs before:** Phase 16.2b (which uses the exceptions + ctx fields added here)

## Goal

Lay the infrastructure that Phase 16.2b (API surface) depends on:
1. `.importlinter` exceptions for new `api → persistence` edges.
2. Two new domain exceptions (`NotFoundError`, `WorkflowRejectedError`).
3. Rejection-flag fields on `PipelineContext`.
4. Updated `HITLGateStepExecutor` that raises `WorkflowRejectedError` when the flag is set.

**This is a small phase by design — infrastructure first, API surface second.**

## CURRENT CODE STATE — Read This First

Phase 16.1 shipped with a DI refactor (commits 0d35671, 55000e9, 82f57fd on
branch `feat/yaml-pipeline`). As a result:

- `PipelineContext` does **not** have a `session` field. `from sqlalchemy.ext.asyncio`
  is forbidden inside `src/engine/` by the `check_raw_sql_in_engine` pre-push
  hook. Do not add `ctx.session` — use `ctx.pattern_repo` / `ctx.qc_history_repo`
  for any persistence from inside engine code, or access the session via
  `WorkflowManager._sessions[workflow_id]` from the api layer.
- `PipelineContext` already has `pattern_repo: PatternRepository | None` and
  `qc_history_repo: QCHistoryRepository | None` (TYPE_CHECKING annotations).
  This phase adds primitive rejection fields alongside them.
- `WorkflowManager._sessions: dict[str, AsyncSession]` already exists at
  `src/api/workflow_manager.py:44`. Phase 16.2b will add a public
  `get_session()` accessor over it — do not duplicate.
- `BaseRepository.commit()` exists (added in 82f57fd) — use
  `await ctx.pattern_repo.commit()` to flush pending writes instead of
  touching a session directly from the engine layer.

If you find yourself importing `AsyncSession` inside `src/engine/`, **stop**
and reach for `ctx.pattern_repo` / `ctx.qc_history_repo` instead.

## Rejection flow design (B4 fix)

**Do NOT call `task.cancel()`** — `asyncio.CancelledError` inherits from `BaseException`, not `Exception`, so `_run_and_cleanup`'s `except Exception` would miss it.

**Instead: rejection-flag pattern.**
1. `PipelineContext` gets two new fields: `rejection_requested: bool = False` and `rejection_reason: str = ""`.
2. `WorkflowManager.reject_workflow` (added in 16.2b) sets these flags, writes audit + feedback, then calls `event.set()` to release the HITL gate.
3. `HITLGateStepExecutor` wakes from `event.wait()`, checks `ctx.rejection_requested`, raises `WorkflowRejectedError(reason)` if true.
4. `WorkflowRejectedError` inherits from `CDDEError → Exception`, so `_run_and_cleanup`'s `except Exception` catches it naturally. FSM transitions to FAILED via the existing code path. No new error handling.

---

## Files to modify

### `.importlinter` (MOD — task 2a.0, must run FIRST)
**Change:** Extend `ignore_imports` on the `api-no-persistence` contract to allow new `feedback_repo` edges.
**Exact change:**
In contract `[importlinter:contract:api-no-persistence]` (line ~176), append to the existing `ignore_imports` block:
```
    src.api.workflow_manager -> src.persistence.feedback_repo
    src.api.services.override_service -> src.persistence.feedback_repo
```
**Constraints:**
- Must run as task 2a.0 (first task in this phase). All subsequent Python changes depend on it.
- Run `uv run lint-imports` immediately after to confirm contracts still parse.
- The `src.api.services.override_service` edge refers to a file created in Phase 16.2b — the exception must exist before that file can be committed.

### `src/domain/exceptions.py` (MOD)
**Change:** Add two new domain exception classes.
**Exact change:** Append to the existing file:
```python
class NotFoundError(CDDEError):
    """Raised when a requested entity (variable, workflow, etc.) does not exist."""

    def __init__(self, entity_type: str, identifier: str) -> None:
        self.entity_type = entity_type
        self.identifier = identifier
        super().__init__(f"{entity_type} '{identifier}' not found")


class WorkflowRejectedError(CDDEError):
    """Raised inside HITLGateStepExecutor when a human rejects the workflow."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Workflow rejected by human: {reason}")
```
**Constraints:**
- Both inherit from `CDDEError → Exception`, NOT from `BaseException`, so the existing `except Exception` in `_run_and_cleanup` catches them.
- `NotFoundError` used by `override_service` (16.2b) for unknown variable.
- `WorkflowRejectedError` used by `HITLGateStepExecutor` (this phase) after the rejection flag is set.

### `src/domain/enums.py` (MOD)
**Change:** Add new `AuditAction` members needed by 16.2b and this phase.
**Exact change:** In the `AuditAction` StrEnum, add:
```python
HUMAN_REJECTED = "human_rejected"
HUMAN_OVERRIDE = "human_override"
```
**Constraints:**
- `HUMAN_REJECTED` is emitted by `HITLGateStepExecutor` (this phase).
- `HUMAN_OVERRIDE` is emitted by `override_service` (16.2b).
- `AgentName.HUMAN` already exists — no change needed.

### `src/engine/pipeline_context.py` (MOD)
**Change:** Add two rejection-tracking fields to the dataclass.
**Exact change:** In the `PipelineContext` dataclass (after the existing fields added in Phase 16.1), append:
```python
rejection_requested: bool = False
rejection_reason: str = ""
```
**Constraints:**
- These fields are **set** by `WorkflowManager.reject_workflow` (16.2b) and **read** by `HITLGateStepExecutor` (this phase). Never mutated elsewhere.
- Default values ensure existing code paths (approve flow) see `rejection_requested=False` and skip the rejection branch.
- No new imports needed — primitive fields.

### `src/engine/step_executors.py` (MOD — `HITLGateStepExecutor`)
**Change:** Check rejection flag after the approval event fires. Raise `WorkflowRejectedError` if set.
**Exact change:** In `HITLGateStepExecutor.execute` (line ~113), after `await approval_event.wait()` (currently line 133), replace the existing approved-path audit record with:
```python
await approval_event.wait()

if ctx.rejection_requested:
    from src.domain.exceptions import WorkflowRejectedError

    ctx.audit_trail.record(
        variable="",
        action=AuditAction.HUMAN_REJECTED,
        agent=AgentName.HUMAN,
        details={"gate": step.id, "reason": ctx.rejection_reason},
    )
    raise WorkflowRejectedError(ctx.rejection_reason)

ctx.audit_trail.record(
    variable="",
    action=AuditAction.HUMAN_APPROVED,
    agent=AgentName.HUMAN,
    details={"gate": step.id},
)
```
**Constraints:**
- Import `WorkflowRejectedError` **inside** the function (not at module top) to avoid circular imports at module load.
- The rejection audit record replaces (not adds to) the approved record on the rejection path — they are mutually exclusive.
- `AuditAction.HUMAN_REJECTED` and `AgentName.HUMAN` are already imported at module top (no new imports needed).

---

## Test constraints

- Add a unit test in `tests/unit/test_step_executors.py` (or create if it doesn't exist) that verifies:
  - `test_hitl_gate_with_rejection_flag_raises_workflow_rejected_error` — build a ctx, set `rejection_requested=True` + `rejection_reason="bad derivation"`, call `HITLGateStepExecutor.execute`, assert raises with correct message.
  - `test_hitl_gate_without_rejection_flag_records_human_approved` — normal approval path still works, audit record emitted.

## Tooling gate

```bash
uv run pyright .
uv run ruff check . --fix
uv run ruff format .
uv run lint-imports
uv run pytest tests/unit/test_step_executors.py -v
uv run pytest
```

## Acceptance criteria

1. ✅ `.importlinter` updated with new `api → persistence` exceptions; `uv run lint-imports` passes.
2. ✅ `NotFoundError` and `WorkflowRejectedError` defined in `src/domain/exceptions.py`, both inherit `CDDEError`.
3. ✅ `AuditAction.HUMAN_REJECTED` and `HUMAN_OVERRIDE` added to the enum.
4. ✅ `PipelineContext.rejection_requested` and `rejection_reason` fields added with safe defaults.
5. ✅ `HITLGateStepExecutor` raises `WorkflowRejectedError` when rejection flag is set; approved path unchanged.
6. ✅ ≥2 new unit tests passing for the gate executor rejection path.
7. ✅ All existing tests still pass (no regressions).
8. ✅ Full tooling gate green.
