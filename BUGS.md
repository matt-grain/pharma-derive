# BUGS — Phase 16 testing findings

Bugs/gaps surfaced during the Phase 16 manual test pass (TEST_PLAN_P16.md). All non-blocking for the demo, all to be addressed in Phase 17 unless escalated.

---

## #1 — `derive_variables` audit attribution misleads on agent provenance

**Surfaced by:** Test 2 re-run (workflow `bfdb3536`, 2026-04-13).

**Symptom (UI):**
- Audit trail Variable column is empty for every step-level event, including `derive_variables`. The 4 variable names are present but buried in `details.variables`, not in the dedicated column.
- `derive_variables` row shows `Agent: orchestrator`. This is technically the dispatcher, but the actual derivation work for AGE_GROUP / TREATMENT_DURATION / IS_ELDERLY / RISK_SCORE is done by the **coder** and **QC** sub-agents (and occasionally the **debugger**) inside the parallel-map body. None of that sub-agent activity appears in the audit trail at all.

**Why it happens (design choice from Fix A):**
- `BuiltinStepExecutor`, `ParallelMapStepExecutor`, `GatherStepExecutor`, `HITLGateStepExecutor` all set `agent=AgentName.ORCHESTRATOR` for their `step_started`/`step_completed` events. The reasoning was: the executor (the runtime that owns the step envelope) is the orchestrator, not any of the sub-agents it spawns. The audit step (an `AgentStepExecutor`) correctly shows `Agent: auditor` because it really is a single-agent step.
- Per-variable provenance currently lives only in the DAG nodes (`approved_code`, `coder_code`, `qc_verdict`) and is surfaced via the Code/DAG tabs — never written to the audit trail.

**Why it matters:**
- Regulatory storytelling for the demo: "show me the audit trail for AGE_GROUP" should produce a row-by-row history of *who* generated what, *when*, with *what verdict*. Currently the audit trail jumps straight from "derive_variables started" → "derive_variables completed" with no intermediate visibility. A reviewer asking "which agent wrote AGE_GROUP's code?" has to switch tabs to the DAG view.
- The orchestrator-only attribution is technically correct at the step envelope level, but **it hides the actual agentic work** — the most interesting part of the system from an interview perspective.

**Proposed fix (Phase 17):**
Emit per-variable audit events from inside `ParallelMapStepExecutor`'s body (or from inside the coder/QC agent invocations themselves). Each event carries:
- `variable=<NAME>` → populates the dedicated column
- `agent=coder|qc|debugger` → correct attribution
- `action=coder_proposed|qc_match|qc_mismatch|debugger_resolved`
- `details=<code snippet, verdict, mismatch row count, etc.>`

Step envelope events (`step_started`/`step_completed` for `derive_variables`) stay as-is on the orchestrator — they're correct at their granularity. The new per-variable events fill in the gap between them.

**Scope estimate:** 30-60 min implementation + tests. Touches `src/engine/step_executors.py` (or the agent invocation site), `src/persistence/orm_models.py` if a new action enum value is needed, plus a couple of unit tests in `tests/unit/test_step_executors.py`.

**Workaround for the demo:** when narrating the audit trail, explicitly call out "the per-variable provenance is in the DAG view — let me show you" and switch tabs. Frame it as a deliberate separation: "audit trail = pipeline lifecycle, DAG view = per-variable code provenance." Reviewers may accept this if framed up-front.

---

## #2 — `/ground_truth` endpoint conflates two distinct 404 states

**Surfaced by:** post-Test-2 bonus check on workflow `bfdb3536` (simple_mock.yaml).

**Symptom:**
```bash
curl http://localhost:8000/api/v1/workflows/bfdb3536/ground_truth
{"detail":"Ground truth check has not been run for this workflow"}
```
But the audit trail clearly shows `step_started` + `step_completed` for `ground_truth_check` at 10:33:15. The step *did* run; it just short-circuited because `simple_mock.yaml` doesn't declare a `ground_truth_path` in its spec.

**Why it matters:**
The endpoint message is now factually wrong in two distinct scenarios:
1. **Workflow hasn't reached `ground_truth_check` yet** — message is correct: "the check has not been run".
2. **Spec has no `ground_truth_path`** — message is misleading: the check *did* run, the report is just empty by design.

A demo viewer who sees the audit trail showing the step ran, then sees the endpoint say "has not been run", will (correctly) conclude the system is lying to them.

**Proposed fix (Phase 17):**
Distinguish the two states in the endpoint handler. Two clean approaches:

1. **Two different 404 messages** based on whether `ctx.ground_truth_report is None` AND the FSM has passed the `ground_truth_check` step:
   ```python
   if ctx.ground_truth_report is None:
       if "ground_truth_check" in completed_steps:
           raise HTTPException(404, "No ground truth report available — spec has no ground_truth_path declared")
       else:
           raise HTTPException(404, "Ground truth check has not yet run for this workflow")
   ```
2. **Return 200 with an empty/skipped report** when the spec opts out, and reserve 404 strictly for "step hasn't run yet". Cleaner REST semantics — "this resource exists, it's just empty" beats "this resource doesn't exist (but it actually does, it's just empty)".

**Scope estimate:** 15-30 min. Single endpoint handler change in `src/api/routers/specs.py` (or wherever `/ground_truth` lives) + 1-2 new tests in the integration suite.

**Workaround for the demo:** if showing simple_mock, don't hit the `/ground_truth` endpoint. Save the GT story for the cdisc demo (Test 1 happy path).

---

## #3 — `WorkflowRejectedError` escapes `_run_and_cleanup` Task wrapper, prints "Task exception was never retrieved" warning

**Surfaced by:** Test 3 (workflow `290eda64`, 2026-04-13). All Test 3 pass criteria still met — this is a noisy log issue, not a functional break.

**Symptom:**
Every successful workflow rejection prints the following to backend stderr:
```
Task exception was never retrieved
future: <Task finished name='Task-1314' coro=<WorkflowManager._run_and_cleanup() done, defined at src/api/workflow_manager.py:81> exception=WorkflowRejectedError('Workflow rejected by human: ...')>
Traceback (most recent call last):
  File "src/api/workflow_manager.py", line 95, in _run_and_cleanup
    await run_with_checkpoint(interpreter, ctx, fsm, session, state_repo, wf_id, started_at)
  File "src/api/workflow_lifecycle.py", line 81, in run_with_checkpoint
    await interpreter.run(on_step_complete=checkpoint)
  File "src/engine/pipeline_interpreter.py", line 75, in run
    await self._execute_step(step)
  File "src/engine/pipeline_interpreter.py", line 95, in _execute_step
    await executor.execute(step, self._ctx)
  File "src/engine/step_executors.py", line 174, in execute
    raise WorkflowRejectedError(ctx.rejection_reason)
src.domain.exceptions.WorkflowRejectedError: Workflow rejected by human: ...
```

**Root cause:**
- `HITLGateStepExecutor.execute` correctly raises `WorkflowRejectedError` on the reject path (Phase 16.2a design)
- The exception propagates through `interpreter.run` → `run_with_checkpoint` → `_run_and_cleanup` → out of the asyncio Task wrapper
- `_run_and_cleanup` does NOT have a top-level `try/except Exception` to catch the rejection before it escapes the Task
- Nothing ever calls `.result()` / `.exception()` on the Task → asyncio prints the "Task exception was never retrieved" warning when the Task is garbage collected
- Cleanup (audit `workflow_failed` event, FSM transition, `workflows_in_progress` decrement) IS happening — likely inside `run_with_checkpoint`'s own `try/finally` or a `done_callback` upstream — so the workflow state stays consistent

**Why it's a bug despite Test 3 passing every assertion:**
- ✅ FSM transitions to `failed` correctly
- ✅ `workflows_in_progress` decrements
- ✅ Audit + FeedbackRow written correctly
- ❌ Every rejection prints a 15-line traceback to stderr that **looks like an unhandled crash** but is actually the happy path
- ❌ In a demo: a reviewer sees the red traceback and assumes the system is broken (terrible look for the reject demo path)
- ❌ In production: log alerts would fire on every user rejection as if it were a crash

**Proposed fix (Phase 17):**
Two clean approaches in `src/api/workflow_manager.py` around line 81-95:

1. **Wrap `_run_and_cleanup` body in `try/except Exception: log + swallow`:**
   ```python
   async def _run_and_cleanup(self, ...) -> None:
       try:
           await run_with_checkpoint(...)
       except WorkflowRejectedError as exc:
           logger.info("Workflow %s rejected: %s", wf_id, exc)
       except Exception:
           logger.exception("Workflow %s failed unexpectedly", wf_id)
       finally:
           # existing cleanup
   ```
   The Task then always completes "successfully" from asyncio's POV. WorkflowRejectedError is now logged at INFO instead of ERROR, distinguishing it from real crashes.

2. **Attach a `done_callback` that retrieves the exception** at task creation time in `/start`:
   ```python
   task = asyncio.create_task(self._run_and_cleanup(...))
   task.add_done_callback(lambda t: t.exception())
   ```
   Less invasive but doesn't solve the "log says ERROR for a happy-path event" problem.

**Recommendation:** option 1 (try/except in `_run_and_cleanup`). Cleaner, fixes both the warning AND the misleading log severity.

**Scope estimate:** 15-30 min implementation + 1 unit test that asserts no warning is printed on the reject path (use `pytest.warns(None)` or capture `sys.stderr`).

**Workaround for the demo:** if rejecting during the demo, narrate it: "you'll see a traceback in the backend log — that's an asyncio warning we know about (Bug #3), not an actual crash. The workflow state on the next slide proves the rejection was clean."

---

## #4 — `CodeEditorDialog` error banner persists across Cancel + reopen

**Surfaced by:** Test 4 Phase 4 (workflow `c7329784`, 2026-04-13). The state-preservation contract from the test plan still passed (code field reverts to original on reopen), but a separate UI state leak was found in passing.

**Symptom:**
1. Open `CodeEditorDialog` for TREATMENT_DURATION (or any variable)
2. Paste broken syntax (e.g. `df[['TREATMENT_DURATION'`), type a reason, click Save Override
3. Backend returns 400, inline red error banner appears: *"400: Derivation failed for 'TREATMENT_DURATION': '[' was never closed (<string>, line 1)"*
4. Click Cancel (or X) to close the dialog
5. Click Edit on the same variable to reopen the dialog
6. **The code field correctly reverts to the original** (state preservation works as designed)
7. **The reason field correctly clears** to placeholder
8. **The Save Override button correctly stays disabled** (code unchanged + no reason)
9. ❌ **The error banner from step 3 is still visible** at the bottom of the reopened dialog — looking exactly like a fresh failure, even though no submission has been made yet

**Root cause (likely):**
`CodeEditorDialog` keeps its `error: string | null` state in a local `useState` that isn't reset on dialog close. Because the parent component conditionally renders the dialog with `{open && <CodeEditorDialog .../>}` (or similar), the dialog may not actually unmount on close — only its visibility flips — so the `useState` value persists across opens. The `code` and `reason` fields likely DO reset because they're keyed off props, but `error` is purely internal.

**Why it matters:**
- A user who corrects their code mentally, closes the dialog to grab a code snippet from elsewhere, and reopens to retry → sees the old error message → confusing
- During the demo: a reviewer watching the override flow could think "the new override failed" when they're actually looking at residue from the previous attempt
- Erodes trust in the UI's freshness signals

**Proposed fix (Phase 17):** three options, in order of cleanliness:
1. **Add `key={variable.name}` to the `<CodeEditorDialog>` element** in the parent — forces React to unmount + remount the dialog when switching variables, naturally clearing all internal state. Caveat: doesn't fix the same-variable case (close + reopen on the same variable still preserves state).
2. **Reset `error` in a `useEffect(() => { setError(null) }, [open])`** inside `CodeEditorDialog` — fires every time the open prop flips. Most surgical fix.
3. **Lift `error` to the parent component** so it's controlled state, then clear it in the parent's `onClose` handler. Architecturally cleanest but most code churn.

**Recommendation:** option 2 (`useEffect` reset on open). 3-line fix in `frontend/src/components/CodeEditorDialog.tsx` + 1 component test asserting the error clears on reopen.

**Scope estimate:** 10-15 min implementation + 1 test.

**Workaround for the demo:** if you trigger the 400 path during the demo, do NOT close+reopen the dialog — fix the code in the same dialog session, or close the dialog and don't reopen the same variable's editor.

---

## #5 — LTM read loop is one-dimensional: `query_patterns` ignores `qc_history` and `feedback` tables (HITL feedback is write-only)

**Surfaced by:** Test 5 follow-up discussion (2026-04-13). The most important architectural finding of the testing session — bigger than Bug #1, arguably the highest-impact item on the BUGS list.

**Symptom (architectural, not a runtime crash):**
We persist three categories of LTM signal across runs, but the coder agent can only read one of them:

| Table | What it stores | Written by | Read by `query_patterns`? | Surfaced to next coder run? |
|---|---|---|---|---|
| `patterns` | Approved code that worked | `save_patterns` builtin | ✅ Yes | ✅ Yes |
| `qc_history` | Coder vs QC mismatches + debugger resolutions per variable per run | `save_patterns` builtin | ❌ No | ❌ No |
| `feedback` | Human approve / reject / override decisions with reasons | HITL endpoints (`approve_with_feedback`, `reject`, `override`) | ❌ No | ❌ No |

`query_patterns` (the only LTM tool wired into the coder agent today) is just a thin wrapper around `PatternRepository.query_by_type` — see `src/agents/tools/query_patterns.py:23`. It returns recent approved code snippets, nothing else. The two richer signal sources sit in the database collecting rows that no agent ever reads.

**Why it matters — the HITL loop is currently theater:**

The whole point of HITL is that human reviewers correct the agent and the agent **learns from the corrections**. Today:
- A reviewer rejects RISK_SCORE with reason "QC mismatch unresolved — debugger could not converge on a safe null-handling strategy" → row written to `feedback` → **next run's coder has zero awareness of this rejection**
- A reviewer overrides AGE_GROUP with `pd.Series(np.select(...))` and reason "Prefer np.select for readability + explicit null handling" → row written to `feedback` → **next run's coder still proposes the original `pd.cut` because that's what the `patterns` table records as the approved version**
- The debugger resolves RISK_SCORE in favor of QC three runs in a row → 3 rows in `qc_history` → **next run's coder repeats the same null-handling mistake because it doesn't know prior coder versions failed**

Effectively: humans correct the agent in the moment, but the agent never carries those corrections forward. The HITL gate becomes a moment-by-moment quality filter rather than a feedback loop. **Every reviewer approval/rejection/override is a write-only side effect.** From a regulatory-AI perspective this is a serious gap — the system's "learning" story today is "the agent gets approved code into a table, and reads its own approved code back later." There's no human-in-the-loop signal in that loop at all.

**Why I missed this initially:**
Test 5 verified `query_patterns` returns rows after 2 runs and assumed that was the full LTM read loop. It IS the full loop *as currently implemented* — but the more important loop (HITL feedback → next agent run) is missing entirely. Bug #1 (per-variable audit attribution) hinted at this — Matt and I both noted the audit trail jumps "derive_variables started → completed" with no per-variable provenance. The same architectural shortcut is at play here: the audit trail and the LTM tools both look at the WRITE side of HITL but never close the READ loop.

**Proposed fix (Phase 17): add two new coder tools — NOT a combined `query_lessons`**

The cleanest fix is to add **two new coder tools** alongside `query_patterns`, each returning a single signal source. The reason for keeping them separate (rather than rolling into one `query_lessons` god-function) is **provenance preservation**: when the LLM sees results from three distinct tools, it knows the origin of each piece of evidence and can weigh them appropriately. A human reviewer's rejection should carry more authority than a prior auto-approved pattern; an unresolved coder/QC disagreement is a different kind of signal than a clean approval. **Collapsing all three into one blob would erase the source distinction and force the model to weigh evidence flat.** Keeping them as separate tools lets the LLM reason about authority: *"the human said no last time → I should not propose that approach"* vs *"the coder and QC agreed last time → safe to repeat"* vs *"the QC and coder disagreed and debugger picked QC → I should generate the QC-style solution."*

1. **`query_feedback(variable_type: str) -> str`** — returns recent rows from `feedback` formatted as:
   ```
   === FEEDBACK 1 (variable=AGE_GROUP, action=overridden, study=simple_mock) ===
   Reason: Prefer np.select for readability + explicit null handling
   The human reviewer replaced the coder's code with a different implementation. Consider this preference when generating new code.

   === FEEDBACK 2 (variable=AGE_GROUP, action=rejected, study=simple_mock) ===
   Reason: too verbose for production audit
   The human reviewer rejected the previous coder's approach. Avoid generating similar code.
   ```

2. **`query_qc_history(variable_type: str) -> str`** — returns recent rows from `qc_history` formatted as:
   ```
   === QC HISTORY 1 (variable=RISK_SCORE, run=c7329784, verdict=mismatch) ===
   Coder approach: np.select with default=None
   QC approach: row-wise apply with explicit pd.notna check
   Debugger resolution: chose QC implementation
   Lesson: edge case on missing IS_ELDERLY — prefer explicit pd.notna
   ```

**Wire both new tools into the coder agent's `tools:` list in `config/agents/coder.yaml`** + update the system prompt to enforce a priority order. Human feedback weighs more than QC history, which weighs more than raw approved patterns:

```yaml
system_prompt: |
  You are a senior statistical programmer...
  Before writing code, query ALL THREE long-term memory sources in this order:

  1. query_feedback — Has a human reviewer rejected or overridden this variable
     before? Their feedback is the STRONGEST signal — adapt your code to their
     preference. A previous rejection means do not propose that approach again.
  2. query_qc_history — Have prior coder/QC versions disagreed on this variable?
     Where did they disagree, and what did the debugger pick? Avoid the same
     edge case.
  3. query_patterns — What approved code exists for this variable? Use it as a
     starting point, but only after you've checked feedback and QC history.

  These signals come from DIFFERENT sources (human reviewer / system QC / prior
  agent runs). Weigh them by authority: human > debugger > prior agent.
```

**Why ordering matters more than enumeration:** the numbered list in the system prompt teaches the LLM that *order encodes weight*. The first tool the prompt mentions gets called first; the LLM treats early signals as higher priority. This is a known PydanticAI pattern (and a general LLM-prompting one). It's the cheapest way to enforce a hierarchy without writing a meta-tool.

**Scope estimate:** 1.5-2 hours total — implementation is small (~50 LoC per tool + repository methods + system prompt update), but the integration test should cover at least 3 scenarios per tool + 1 end-to-end test that proves a 2nd run's coder *behavior* differs after a 1st run rejected the original approach. The behavioral test is hard to write deterministically (LLM nondeterminism), but a `FunctionModel`-based test asserting the new tools are called would be enough proof for the demo.

**Why this is the most important Phase 17 item:**
- Bug #1 is a UI/audit storytelling gap (visible to reviewers but not load-bearing)
- Bug #2, #3, #4 are cosmetic/log/state issues
- **Bug #5 is the architectural gap that makes the entire HITL story credible (or not).** A reviewer asking "how does your system learn from human corrections?" is a question this gap answers with "it doesn't, today" — which would invalidate a major demo claim.

**Workaround for the demo:** be honest about the scope. Frame the current LTM as "Phase 16 ships the patterns side of the loop — feedback and QC history are persisted but not yet surfaced to the agent. Phase 17 closes the loop." This is a credible roadmap statement and is much better than getting blindsided by the question on stage.
