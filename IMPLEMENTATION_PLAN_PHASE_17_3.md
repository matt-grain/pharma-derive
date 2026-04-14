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

**IMPORTANT — verified state of `src/api/routers/workflows.py:136-150` before this fix:**
- Endpoint at line 136: `@router.get("/{workflow_id}/ground_truth", response_model=GroundTruthReportResponse, status_code=200)`
- Function `get_ground_truth(workflow_id, manager: WorkflowManagerDep) -> GroundTruthReportResponse` at line 137-140
- Currently calls `ctx = manager.get_context(workflow_id)` at line 142 — does NOT call `manager.get_interpreter(workflow_id)`
- Single 404 at line 146-149 with detail `"Ground truth check has not been run for this workflow"`

**Exact change:**
1. Update `get_ground_truth` to ALSO fetch the interpreter (needed for `completed_steps` access):
   ```python
   ctx = manager.get_context(workflow_id)
   interpreter = manager.get_interpreter(workflow_id)
   if ctx is None or interpreter is None:
       raise HTTPException(status_code=404, detail=f"Workflow {workflow_id!r} not found")
   ```
2. Replace the current single-message 404 (lines 145-149) with the two-state logic:
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
3. **`PipelineInterpreter.completed_steps` does NOT exist — verified.** Reading `src/engine/pipeline_interpreter.py`, only `current_step` (line 41-44) is exposed. There is NO internal `_completed_steps` list either. **You MUST add the property** as part of this fix:
   - In `PipelineInterpreter.__init__` (around line 29-39), add a new instance attribute: `self._completed_steps: list[StepDefinition] = []`
   - Inside `run()` (around line 50-80), after each successful `await self._execute_step(step)` call (line 75), append to the list: `self._completed_steps.append(step)`
   - Add a public property below `current_step`:
     ```python
     @property
     def completed_steps(self) -> list[StepDefinition]:
         """Steps that have completed successfully so far in this run."""
         return list(self._completed_steps)
     ```
4. Add a unit test in `tests/unit/test_pipeline_interpreter.py` asserting the property reflects the run state correctly: `test_completed_steps_lists_steps_in_completion_order` (build a 3-step pipeline, run it, assert `interpreter.completed_steps == [step1, step2, step3]`)

**Constraints:**
- HTTPException detail strings should be the EXACT strings shown above (the test plan asserts them via Test 1 §5 negative path)
- Don't change the response_model or status_code of the endpoint
- Add new test cases (see test specs below)

#### `tests/integration/test_ground_truth_runtime.py` (MODIFY — file already exists, confirmed)
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

#### `frontend/src/components/CodePanel.tsx` (MODIFY — Bug #4)
**Change:** Clear the override-error state in the parent's `onOpenChange(false)` handler so the error banner doesn't persist across dialog close + reopen.

**IMPORTANT — file location correction:** `<CodeEditorDialog>` is mounted in `frontend/src/components/CodePanel.tsx:77`, NOT in `frontend/src/pages/WorkflowDetailPage.tsx`. Verified via grep: `WorkflowDetailPage.tsx` has zero references to `CodeEditorDialog`. The override mutation hook is `useOverrideVariable` from `@/hooks/useWorkflows` (imported at `CodePanel.tsx:6`).

**Verified state of `frontend/src/components/CodePanel.tsx:77-79` before this fix:**
```tsx
<CodeEditorDialog
  open={editingVariable === node.variable}
  onOpenChange={(open) => { if (!open) setEditingVariable(null) }}
```
The dialog is conditionally open via the `editingVariable === node.variable` predicate. The `onOpenChange` already clears `editingVariable` on close. The bug is that the `error` prop passed into `<CodeEditorDialog>` (sourced from `useOverrideVariable` mutation state — likely `mutation.error?.message`) is NOT cleared on close.

**Exact change:**
1. **Locate the source of the `error` prop** passed to `<CodeEditorDialog>` (currently somewhere around line 77-85 of `CodePanel.tsx`). It is likely either:
   - A direct read from the mutation: `error={mutation.error?.message ?? null}`
   - A local state variable: `const [error, setError] = useState<string | null>(null)` set in the mutation's `onError` callback
2. **If it's a local state variable**, update the existing `onOpenChange` handler to ALSO clear it:
   ```tsx
   onOpenChange={(open) => {
     if (!open) {
       setEditingVariable(null)
       setError(null)  // NEW — clear stale error from previous failed submission
     }
   }}
   ```
3. **If it's a direct read from `mutation.error`**, the fix is to call `mutation.reset()` in the close handler instead (TanStack Query's mutation reset clears the error state):
   ```tsx
   onOpenChange={(open) => {
     if (!open) {
       setEditingVariable(null)
       mutation.reset()  // NEW — TanStack Query reset clears error AND data
     }
   }}
   ```
4. **Verify by grepping the file** — find the exact source of the `error={...}` prop and apply whichever pattern matches.

**Constraints:**
- Don't refactor the dialog component itself — the fix is purely in the parent's state management
- Don't introduce a `useEffect` for this — the imperative cleanup in the close handler is the cleanest approach (and the project's ESLint config bans `react-hooks/set-state-in-effect`)
- Preserve the existing component patterns (no new abstractions for a 2-line fix)
- Use `mutation.reset()` if the project follows TanStack Query idioms — it's preferred over manual local state for mutation errors

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
1. Bug #2 — Add `completed_steps` property to `PipelineInterpreter` in `src/engine/pipeline_interpreter.py` (verified does NOT exist today). Append to `_completed_steps` list inside `run()` after each successful `_execute_step`.
2. Bug #2 — Add unit test `test_completed_steps_lists_steps_in_completion_order` in `tests/unit/test_pipeline_interpreter.py`
3. Bug #2 — Update `src/api/routers/workflows.py:get_ground_truth` (lines 137-150) to ALSO call `manager.get_interpreter(workflow_id)` and emit dual 404 messages
4. Bug #2 — Add 2 new tests in `tests/integration/test_ground_truth_runtime.py` (file already exists — verified)
5. Bug #3 — Update `src/api/workflow_manager.py::_run_and_cleanup` (lines 81-115) with the dedicated `except WorkflowRejectedError` block BEFORE the existing `except Exception`
6. Bug #3 — Add 1 new test in `tests/unit/test_workflow_manager.py` for the no-warning assertion
7. Run the backend tooling gate (pyright + ruff + lint-imports + pytest)

**Frontend second** (one `vite-react` dispatch):
8. Bug #4 — Update `frontend/src/components/CodePanel.tsx` (the file that mounts `<CodeEditorDialog>` at line 77 — verified). Use `mutation.reset()` from `useOverrideVariable` if the error sources from a TanStack Query mutation, or `setError(null)` if it's a local state variable — grep the file to determine which.
9. Bug #4 — Add 1 new test in `frontend/src/components/CodeEditorDialog.test.tsx`
10. Run the frontend tooling gate (`npx tsc -b --noEmit && npm run lint && npm run test`)

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
npx tsc -b --noEmit
npm run lint
npm run test
```
**Note:** The frontend `package.json` does NOT define a `typecheck` script — verified. Use `npx tsc -b --noEmit` directly. The `npm run build` script also runs `tsc -b` as part of the build, but is slower because it also runs the full Vite build.

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
