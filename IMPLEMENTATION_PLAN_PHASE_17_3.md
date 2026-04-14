# Phase 17.3 — Cleanup Bundle (Bugs #2, #3, #4)

**Bugs:** BUGS.md #2 (`/ground_truth` 404 conflates two states), #3 (`_run_and_cleanup` lets `WorkflowRejectedError` escape Task wrapper), #4 (`CodeEditorDialog` error banner persists across cancel + reopen).

**Goal:** Three small, independent fixes bundled into one phase. Each is too small to justify its own phase, and they touch disjoint files so they cannot conflict.

**Agents:** `python-fastapi` for Bugs #2 + #3 (backend); `vite-react` for Bug #4 (frontend). Dispatch backend first, then frontend.
**Depends on:** Nothing (independent of 17.1 and 17.2)
**Estimated effort:** 45–60 min total (15-30 min for #2, 15-30 min for #3, 10-15 min for #4)
**Reference (read first):** BUGS.md §#2 §#3 §#4

---

## Sub-bundle A — Backend (Bugs #2 + #3) — `python-fastapi`

### Files to modify — 3 modified

#### `src/api/routers/workflows.py` (MODIFY — Bug #2)
**Change:** Distinguish two distinct 404 states for the `/ground_truth` endpoint: "step hasn't run yet" vs "spec has no ground_truth_path declared".
**Exact change:**
1. Find the function that handles `GET /workflows/{workflow_id}/ground_truth` (search for `ground_truth` or `def get_ground_truth`)
2. Replace the current single-message 404 with the two-state logic:
   ```python
   if ctx.ground_truth_report is None:
       # Distinguish "step hasn't run yet" from "spec has no ground_truth_path"
       completed_step_ids = {s.id for s in interpreter.completed_steps}
       if "ground_truth_check" in completed_step_ids:
           raise HTTPException(
               status_code=404,
               detail="No ground truth report available — spec has no ground_truth_path declared",
           )
       raise HTTPException(
           status_code=404,
           detail="Ground truth check has not yet run for this workflow",
       )
   ```
3. **Verify the FSM exposes a way to query completed steps.** The `interpreter.completed_steps` accessor MAY NOT exist — check `src/engine/pipeline_interpreter.py`. If it doesn't:
   - **Option 1:** add a `completed_steps: list[StepDefinition]` property on `PipelineInterpreter` that exposes the internal completed-steps list
   - **Option 2:** check the audit trail for a `STEP_COMPLETED` event with `details.step == "ground_truth_check"` — but this requires an audit_trail iteration which is more expensive
   - **Choose Option 1** — cleaner, more direct, and the property is useful for other callers
4. If you add `completed_steps` to `PipelineInterpreter`, also update `src/engine/pipeline_interpreter.py` and add a unit test in `tests/unit/test_pipeline_interpreter.py` asserting the property reflects the run state correctly

**Constraints:**
- HTTPException detail strings should be the EXACT strings shown above (the test plan asserts them via Test 1 §5 negative path)
- Don't change the response_model or status_code of the endpoint
- Add new test cases (see test specs below)

#### `tests/integration/test_workflows_router.py` or `tests/integration/test_ground_truth_endpoint.py` (MODIFY or CREATE)
**Tests to add (at least 2 new):**

1. **`test_ground_truth_endpoint_returns_404_with_premature_message_when_step_not_run`**
   - Arrange: start a workflow, immediately query `/ground_truth` before the workflow reaches `ground_truth_check`
   - Act: GET `/api/v1/workflows/{wf_id}/ground_truth`
   - Assert: status 404, `detail` exactly equals `"Ground truth check has not yet run for this workflow"`

2. **`test_ground_truth_endpoint_returns_404_with_no_path_message_when_spec_lacks_ground_truth_path`**
   - Arrange: run a `simple_mock.yaml` workflow to completion (no `ground_truth_path` in the spec, the step runs but short-circuits)
   - Act: GET `/api/v1/workflows/{wf_id}/ground_truth`
   - Assert: status 404, `detail` exactly equals `"No ground truth report available — spec has no ground_truth_path declared"`

**Constraints:** AAA markers, specific exception types, named test_<action>_<scenario>_<expected>.

---

#### `src/api/workflow_manager.py` (MODIFY — Bug #3)
**Change:** Add a dedicated `except WorkflowRejectedError` handler in `_run_and_cleanup` that catches the rejection BEFORE the generic `except Exception` and does NOT re-raise. This stops the asyncio "Task exception was never retrieved" warning by ensuring the exception is consumed inside the task body.
**Exact change:**
1. Find `_run_and_cleanup` (lines 81-115 in current file)
2. The current structure is:
   ```python
   try:
       await run_with_checkpoint(...)
       fsm.complete()
       ...
       return result
   except Exception as exc:
       logger.exception("Workflow {wf_id} failed", wf_id=wf_id)
       record_failure_audit(ctx, exc, interpreter.current_step)
       fsm.fail(str(exc))
       ...
       raise
   finally:
       ...
   ```
3. Insert a **new `except WorkflowRejectedError` block BEFORE** the existing `except Exception`:
   ```python
   except WorkflowRejectedError as exc:
       logger.info("Workflow {wf_id} rejected by human: {reason}", wf_id=wf_id, reason=str(exc))
       record_failure_audit(ctx, exc, interpreter.current_step)
       fsm.fail(str(exc))
       self._completed_at[wf_id] = datetime.now(UTC).isoformat()
       await persist_error_state(state_repo, session, wf_id, ctx, started_at, self._completed_at[wf_id])
       # Intentionally do NOT re-raise — rejection is a happy path, not an unexpected failure.
       # Returning a build_result here so the task completes "successfully" from asyncio's POV.
       return build_result(wf_id, ctx, fsm)
   except Exception as exc:
       # ... existing block unchanged
       raise
   ```
4. Add the import at the top (in the runtime imports, NOT under TYPE_CHECKING):
   ```python
   from src.domain.exceptions import WorkflowRejectedError
   ```
   (Note: `WorkflowRejectedError` is already used in `step_executors.py:166-174`, so the import path is established.)

**Constraints:**
- Logger level for rejection MUST be `INFO`, not `ERROR` or `EXCEPTION` (the current `logger.exception` would be misleading — rejection is intentional)
- The `return build_result(...)` is intentional — it makes the task completion "clean" from asyncio's POV
- The `except Exception` block MUST stay as-is (raise) to handle truly unexpected failures
- Order matters: `WorkflowRejectedError` MUST come BEFORE `Exception` (Python catches the first matching handler)
- The `finally` block stays unchanged — it always runs

#### `tests/unit/test_workflow_manager.py` (MODIFY)
**Test to add:**
- **`test_reject_workflow_does_not_emit_task_exception_warning`**
  - Arrange: build a `WorkflowManager`, start a workflow, wait for HITL gate, call `reject_workflow(wf_id, "test rejection")`
  - Act: wait for the workflow task to complete
  - Assert:
    1. Workflow status is `failed` (existing behavior)
    2. `pytest.warns(None)` context — assert NO warnings were raised during the rejection (specifically, no `RuntimeWarning` about "Task exception was never retrieved")
    3. Backend log captured via `caplog` shows `INFO` level message `"Workflow ... rejected by human"` and NO `ERROR` level message for this workflow
- Use `caplog` fixture from pytest for log assertions

**Alternative approach if `pytest.warns(None)` is too brittle:**
- Capture stderr via `capsys.readouterr().err` and assert the string `"Task exception was never retrieved"` is NOT in it

**Constraints:**
- Real assertions on observable behavior, not internal state
- Must use a real (in-memory) workflow with a real HITL gate, not mocks of the manager itself

---

## Sub-bundle B — Frontend (Bug #4) — `vite-react`

### Files to modify — 2 modified

#### `frontend/src/pages/WorkflowDetailPage.tsx` (MODIFY — Bug #4)
**Change:** Clear the override-error state in the parent's `onOpenChange(false)` handler so the error banner doesn't persist across dialog close + reopen.
**Exact change:**
1. Find where `<CodeEditorDialog ... />` is rendered (search for `CodeEditorDialog` in the file)
2. Find the state declaration that holds the error message (likely something like `const [overrideError, setOverrideError] = useState<string | null>(null)` — could be named differently, locate it by following the `error` prop passed into `<CodeEditorDialog>`)
3. The current `onOpenChange` prop is probably `onOpenChange={setEditorOpen}` or similar — change it to a function that clears the error on close:
   ```tsx
   onOpenChange={(open: boolean) => {
     setEditorOpen(open)
     if (!open) {
       setOverrideError(null)  // clear stale error from any previous failed submission
     }
   }}
   ```
4. **Also clear the error when starting a new mutation** (so the banner from a prior failure doesn't show until the new failure completes). Find the `onSave` callback passed to `<CodeEditorDialog>` and at the start of it:
   ```tsx
   onSave={(newCode, reason) => {
     setOverrideError(null)  // clear any prior error before submitting
     overrideMutation.mutate({ workflowId, variable: editingVariable, newCode, reason })
   }}
   ```

**Constraints:**
- Don't refactor the dialog component itself — the fix is purely in the parent's state management
- Don't introduce a `useEffect` for this — the imperative cleanup in the close handler is the cleanest approach (and the project's ESLint config bans `react-hooks/set-state-in-effect`)
- Preserve the existing component patterns (no new abstractions for a 2-line fix)

#### `frontend/src/components/CodeEditorDialog.test.tsx` (MODIFY)
**Test to add:**
- **`it("should not display previous error after dialog is closed and reopened")`**
  - Arrange: render the component once with `error="400: syntax error"`, simulate the close + reopen by re-rendering with `open={false}` then `open={true}` AND with `error={null}` (since the parent should have cleared it on close)
  - Act: query for the error banner
  - Assert: the error banner is NOT in the document after reopen
- **Optionally also add a test on `WorkflowDetailPage.test.tsx`** that verifies the parent clears the error state when the dialog closes — but this requires more setup. The component-level test above is sufficient if it asserts that `error={null}` results in no banner.

**Constraints:**
- React Testing Library queries by role/text/label — never by class or `data-testid`
- Test name follows `it("should <behavior> when <scenario>")`
- Use `userEvent` for simulated interactions, not raw `fireEvent`

---

## Implementation order (within Phase 17.3)

**Backend first** (one `python-fastapi` dispatch):
1. Bug #2 — Update `src/api/routers/workflows.py` for the dual 404 logic + add `completed_steps` property to `PipelineInterpreter` if missing
2. Bug #2 — Add 2 new tests in `tests/integration/test_workflows_router.py` (or wherever the ground_truth endpoint test lives)
3. Bug #3 — Update `src/api/workflow_manager.py::_run_and_cleanup` with the dedicated `except WorkflowRejectedError` block
4. Bug #3 — Add 1 new test in `tests/unit/test_workflow_manager.py` for the no-warning assertion
5. Run the backend tooling gate (pyright + ruff + lint-imports + pytest)

**Frontend second** (one `vite-react` dispatch):
6. Bug #4 — Update `frontend/src/pages/WorkflowDetailPage.tsx` (or wherever `<CodeEditorDialog>` is mounted) to clear error on close and on new mutation
7. Bug #4 — Add 1 new test in `frontend/src/components/CodeEditorDialog.test.tsx`
8. Run the frontend tooling gate (`npm run typecheck && npm run lint && npm run test`)

---

## Tooling gate (mandatory after Phase 17.3)

**Backend** (after sub-bundle A):
```bash
cd C:\Projects\Interviews\jobs\Sanofi-AI-ML-Lead\homework
uv run pyright .
uv run ruff check . --fix
uv run ruff format .
uv run lint-imports
uv run pytest tests/ -q
```

**Frontend** (after sub-bundle B):
```bash
cd C:\Projects\Interviews\jobs\Sanofi-AI-ML-Lead\homework\frontend
npm run typecheck
npm run lint
npm run test
```

---

## Acceptance criteria for Phase 17.3

**Bug #2:**
- ✅ `/ground_truth` endpoint returns 404 with `"Ground truth check has not yet run for this workflow"` when the workflow hasn't reached the step yet
- ✅ `/ground_truth` endpoint returns 404 with `"No ground truth report available — spec has no ground_truth_path declared"` when the step ran but the spec has no path
- ✅ 2 new integration tests assert both messages
- ✅ `PipelineInterpreter.completed_steps` property exists (if it didn't already)

**Bug #3:**
- ✅ `_run_and_cleanup` has a dedicated `except WorkflowRejectedError` handler
- ✅ Logger level for rejection is `INFO`, not `ERROR`
- ✅ The handler does NOT re-raise (returns `build_result(...)` instead)
- ✅ 1 new unit test asserts no `"Task exception was never retrieved"` warning is printed during the reject path
- ✅ Manual smoke test: re-run TEST_PLAN_P16.md Test 3 against the post-Phase-17.3 build → backend log shows NO traceback for the rejected workflow

**Bug #4:**
- ✅ `WorkflowDetailPage` clears the override error state when the dialog closes
- ✅ `WorkflowDetailPage` clears the override error state when a new mutation starts
- ✅ 1 new component test asserts the error banner does NOT show after dialog close + reopen
- ✅ Manual smoke test: re-run TEST_PLAN_P16.md Test 4 Phase 4 → trigger 400 syntax error → close dialog → reopen → verify error banner is gone

**Phase 17.3 as a whole:**
- ✅ All 18 pre-push hooks green
- ✅ Total backend test count increases by 3 (2 for Bug #2 + 1 for Bug #3)
- ✅ Total frontend test count increases by 1 (Bug #4)

**This phase closes Bugs #2, #3, and #4.**
