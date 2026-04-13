# Phase 16.2b — HITL Backend API Surface

**Agent:** `python-fastapi`
**Depends on:** Phase 16.2a (exceptions, ctx fields, HITLGateStepExecutor update, importlinter exceptions)
**Fixes:** §5C.3 (approvals), §5C.5 (feedback capture), §9.4 (HITL design)

## Goal

With 16.2a's plumbing in place, add the API surface:
1. **Rich approval payload** — `POST /approve` accepts optional per-variable decisions + free-text reason.
2. **Reject endpoint** — `POST /reject` fails the workflow via the rejection-flag pattern from 16.2a.
3. **Variable override** — `POST /variables/{var}/override` lets humans rewrite approved code, re-executes it.
4. **All human actions persist to `FeedbackRepository`** — closing the cross-run learning loop.

**Out of scope:** UI changes (Phase 16.3).

## CURRENT CODE STATE — Read This First

Phase 16.1 shipped with a DI refactor. Key facts for this phase:

- `PipelineContext` has **no** `session` field. Do **not** access `ctx.session`
  anywhere. The session lives only on `WorkflowManager._sessions[workflow_id]`
  and on the `PatternRepository` / `QCHistoryRepository` instances already
  wired into `PipelineContext` by `src/factory.py`.
- `WorkflowManager._sessions: dict[str, AsyncSession]` exists at
  `src/api/workflow_manager.py:44`. The new `get_session(workflow_id)` method
  you are adding is just a public accessor over that dict.
- `src/api/services/override_service.py` is in the `src/api/` tree, so it
  **is** allowed to import `AsyncSession` and `FeedbackRepository` directly
  (verified by the relevant `.importlinter` exception added in 16.2a). Do
  not try to route the session through `ctx.session` — it doesn't exist.
- `src/api/workflow_manager.py` is already **238 lines** (over the 200-line
  soft limit set by `check_file_length`). Adding the three new methods
  (`get_session`, `approve_with_feedback`, `reject_workflow`) will push it
  further. **Before** adding code, check `wc -l src/api/workflow_manager.py`
  and `wc -l src/api/workflow_lifecycle.py`. If the limit check fails on push,
  extract an `src/api/workflow_hitl.py` helper module (mirroring the
  `workflow_lifecycle` extraction from commit 3a8ee62) that owns the
  approve/reject/session-access logic, and have `WorkflowManager` delegate
  to it. Do not bypass the size check with `# noqa` or similar.

---

## Files to create

### `src/api/services/override_service.py` (NEW)
**Purpose:** Service-layer helper for the variable-override flow. Keeps the router thin.
**Dependencies (constructor params):** `session: AsyncSession`
**Public methods:**
- `async def override_variable(self, ctx: PipelineContext, variable: str, new_code: str, reason: str) -> DAGNodeOut`
  - Validate variable exists in DAG (raise `NotFoundError("variable", variable)` if not).
  - Run `execute_derivation(ctx.derived_df, new_code, list(ctx.derived_df.columns))`.
  - If execution fails, raise `DerivationError(variable, exec_result.error or "unknown")`. DO NOT mutate `node.approved_code`.
  - On success: update `node.approved_code = new_code`, call `apply_series_to_df(variable, exec_result, ctx.derived_df)`, record audit, write `FeedbackRepository` row, commit session.
  - Return the updated node serialized as `DAGNodeOut` schema.
**Constraints:**
- Raises domain exceptions (`NotFoundError`, `DerivationError`), never `HTTPException`.
- `apply_series_to_df` is a **standalone module function** in `src/engine/debug_runner.py`, NOT a method on `DerivationDAG`. Import: `from src.engine.debug_runner import apply_series_to_df`.
- Execute-then-persist order: validate the new code works BEFORE mutating state.
- Commit once at the end (both audit trail + feedback row in one transaction).
**Reference:** `src/engine/derivation_runner.py::_approve_no_qc` (line 66-85) — similar pattern of executing code + applying to df.
**Layer note:** `src/api/services/override_service.py` imports from `src.engine.debug_runner` — allowed (api → engine is not forbidden). Imports from `src.persistence.feedback_repo` — allowed via the new `.importlinter` exception added in 16.2a.

### `tests/integration/test_hitl_flows.py` (NEW)
**Purpose:** Integration tests for the expanded HITL surface.
**Tests to write:**
- `test_reject_workflow_fails_fsm_and_writes_feedback` — start workflow, get to HITL gate, POST /reject with reason, assert FSM reaches FAILED, assert FeedbackRow exists with reason, assert `WORKFLOW_FAILED` audit action present.
- `test_reject_without_reason_returns_422` — POST /reject with empty string reason, assert 422 (enforced by `Field(min_length=1)`).
- `test_approve_with_per_variable_payload_writes_feedback` — POST /approve with body `{variables: [{var: "AGEGR1", approved: true, note: "ok"}], reason: "good"}`, assert FeedbackRow for each variable.
- `test_approve_with_no_body_still_works_backwards_compat` — POST /approve with no JSON body, assert it still releases the gate (backwards compat).
- `test_override_variable_rewrites_approved_code` — POST /variables/AGEGR1/override with valid new code, assert DAGNode.approved_code updated and HUMAN_OVERRIDE audit record present.
- `test_override_variable_with_invalid_code_returns_400` — POST /override with syntax-broken code, assert 400 + original approved_code preserved.
- `test_override_variable_for_unknown_variable_returns_404` — unknown var name, assert 404.
- `test_reject_on_already_completed_workflow_returns_409` — workflow already done, assert 409.
**Fixtures:** Reuse `async_client` + mock LLM fixture from existing integration tests. Seed a workflow that reaches the HITL gate using the same setup as `tests/integration/test_workflow.py`.

---

## Files to modify

### `src/api/schemas.py` (MOD)
**Change:** Add 4 new request/response schemas.
**Exact change:** Append after `WorkflowStatusResponse`:
```python
class VariableDecision(BaseModel, frozen=True):
    """Per-variable approval decision from the human reviewer."""

    variable: str
    approved: bool
    note: str | None = None


class ApprovalRequest(BaseModel, frozen=True):
    """Optional payload for POST /approve — defaults to approve-all if omitted."""

    variables: list[VariableDecision] = []
    reason: str | None = None


class RejectionRequest(BaseModel, frozen=True):
    """Required payload for POST /reject."""

    reason: str = Field(min_length=1)


class VariableOverrideRequest(BaseModel, frozen=True):
    """Payload for POST /variables/{var}/override."""

    new_code: str = Field(min_length=1)
    reason: str = Field(min_length=1)
```
Add `from pydantic import BaseModel, Field` at the top of the file if `Field` isn't already imported.
**Constraints:**
- All models frozen.
- `ApprovalRequest` fields default to empty (backwards compat with existing `/approve` that takes no body).
- `RejectionRequest.reason` and `VariableOverrideRequest.*` enforce non-empty via `Field(min_length=1)` — FastAPI auto-generates 422 on violation.

### `src/api/workflow_manager.py` (MOD)
**Change:** Add `get_session`, `approve_with_feedback`, `reject_workflow` methods.
**Exact change:**
```python
def get_session(self, workflow_id: str) -> AsyncSession | None:
    """Return the live AsyncSession for an active workflow, or None."""
    return self._sessions.get(workflow_id)

async def approve_with_feedback(
    self,
    workflow_id: str,
    payload: ApprovalRequest | None,
) -> None:
    """Set the HITL approval event AND persist feedback to the repository."""
    event = self.get_approval_event(workflow_id)
    if event is None:
        raise KeyError("not_awaiting_approval")
    session = self._sessions.get(workflow_id)
    ctx = self._contexts.get(workflow_id)
    if payload is not None and session is not None and ctx is not None and ctx.spec is not None:
        from src.persistence.feedback_repo import FeedbackRepository

        repo = FeedbackRepository(session)
        study = ctx.spec.metadata.study
        for decision in payload.variables:
            await repo.store(
                variable=decision.variable,
                feedback=decision.note or payload.reason or "",
                action_taken="approved" if decision.approved else "rejected",
                study=study,
            )
        await session.commit()
    event.set()

async def reject_workflow(self, workflow_id: str, reason: str) -> None:
    """Flag the workflow for rejection. HITLGateStepExecutor raises WorkflowRejectedError after the gate releases."""
    ctx = self._contexts.get(workflow_id)
    if ctx is None:
        raise KeyError("workflow_not_found")
    event = self.get_approval_event(workflow_id)
    if event is None:
        raise KeyError("not_awaiting_approval")

    # Set the rejection flag BEFORE releasing the gate — the step executor checks it after event.wait() returns.
    ctx.rejection_requested = True
    ctx.rejection_reason = reason

    session = self._sessions.get(workflow_id)
    if session is not None and ctx.spec is not None:
        from src.persistence.feedback_repo import FeedbackRepository

        repo = FeedbackRepository(session)
        await repo.store(
            variable="",
            feedback=reason,
            action_taken="rejected",
            study=ctx.spec.metadata.study,
        )
        await session.commit()

    # Release the HITL gate. The step executor wakes up, raises WorkflowRejectedError,
    # which bubbles into _run_and_cleanup's `except Exception`. FSM.fail() runs there.
    event.set()
```
**Constraints:**
- **Runtime import of `ApprovalRequest`** — add `from src.api.schemas import ApprovalRequest` at module top. NOT TYPE_CHECKING. The method body reads `payload.variables` at runtime. No circular dep (`src.api.schemas` does not import `src.api.workflow_manager`).
- Use `AuditAction` / `AgentName` enum members, never string literals.
- Null-check session, ctx, and ctx.spec before using.
- **Do NOT call `task.cancel()`.** The rejection flag + `WorkflowRejectedError` in the step executor is the approved error path (16.2a).
- `FeedbackRepository` import lives inside the function body to keep the module-level import surface narrow (matches the existing pattern for `WorkflowStateRepository`).

### `src/api/routers/workflows.py` (MOD)
**Change:** Update existing `/approve`, add `/reject`, add `/variables/{var}/override`.
**Exact change:**

1. Modify existing `/approve`:
```python
@router.post("/{workflow_id}/approve", response_model=WorkflowStatusResponse, status_code=200)
async def approve_workflow(
    workflow_id: str,
    manager: WorkflowManagerDep,
    payload: ApprovalRequest | None = None,
) -> WorkflowStatusResponse:
    """Approve a workflow at the HITL gate — optionally with per-variable feedback."""
    ctx = manager.get_context(workflow_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id!r} not found")
    try:
        await manager.approve_with_feedback(workflow_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=409, detail="Workflow is not awaiting approval") from exc
    return _build_status_response(workflow_id, manager)
```

2. New `/reject`:
```python
@router.post("/{workflow_id}/reject", response_model=WorkflowStatusResponse, status_code=200)
async def reject_workflow_endpoint(
    workflow_id: str,
    payload: RejectionRequest,
    manager: WorkflowManagerDep,
) -> WorkflowStatusResponse:
    """Reject a workflow at the HITL gate — fails the FSM with the provided reason."""
    try:
        await manager.reject_workflow(workflow_id, payload.reason)
    except KeyError as exc:
        code = 404 if "workflow_not_found" in str(exc) else 409
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _build_status_response(workflow_id, manager)
```

3. New `/variables/{var}/override`:
```python
@router.post(
    "/{workflow_id}/variables/{variable}/override",
    response_model=DAGNodeOut,
    status_code=200,
)
async def override_variable(
    workflow_id: str,
    variable: str,
    payload: VariableOverrideRequest,
    manager: WorkflowManagerDep,
) -> DAGNodeOut:
    """Override a derivation's approved code with human-edited code."""
    ctx = manager.get_context(workflow_id)
    session = manager.get_session(workflow_id)
    if ctx is None or session is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id!r} not found")

    from src.api.services.override_service import OverrideService
    from src.domain.exceptions import DerivationError, NotFoundError

    service = OverrideService(session)
    try:
        return await service.override_variable(ctx, variable, payload.new_code, payload.reason)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DerivationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
```

**Constraints:**
- Import new schemas (`ApprovalRequest`, `RejectionRequest`, `VariableOverrideRequest`) at top of file alongside existing schema imports.
- Keep existing `/approve` signature backwards compatible — `payload=None` means "just release the gate".
- Use domain exception → HTTP mapping (not `HTTPException` inside the service).
- `DAGNodeOut` schema already exists in `src/api/schemas.py:64` — no new schema needed for the override response.

---

## Tooling gate

```bash
uv run pyright .
uv run ruff check . --fix
uv run ruff format .
uv run pytest tests/integration/test_hitl_flows.py -v
uv run pytest
uv run lint-imports
```

## Acceptance criteria

1. ✅ `POST /approve` with `ApprovalRequest` body writes per-variable `FeedbackRow`s.
2. ✅ `POST /approve` without body still releases the HITL gate (backwards compat).
3. ✅ `POST /reject` with reason sets the rejection flag; `HITLGateStepExecutor` raises `WorkflowRejectedError`; FSM transitions to FAILED via existing `except Exception` path.
4. ✅ `POST /reject` with empty reason returns 422.
5. ✅ `POST /variables/{var}/override` executes new code, updates `DAGNode.approved_code` on success, preserves original on failure, writes `HUMAN_OVERRIDE` audit + `FeedbackRow`.
6. ✅ Override on unknown variable → 404, invalid code → 400.
7. ✅ **No `asyncio.CancelledError` paths** — rejection uses the flag pattern exclusively.
8. ✅ All existing tests still pass.
9. ✅ ≥8 new integration tests passing, including one that specifically verifies the rejection flow transitions FSM to FAILED cleanly.
10. ✅ Full tooling gate green.
