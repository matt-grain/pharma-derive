# Phase 16 — Manual Test Plan

**Branch:** `feat/yaml-pipeline`
**HEAD:** `40d30ac` (Phase 16.5 cleanup) + uncommitted fix bundle A/B/C from the Test 2 session
**Totals:** 298 backend tests + 13 frontend = 311 passing (after the A/B/C fix bundle; was 297+13 at HEAD)
**Status of this plan:**
- ✅ **Test 2 — Rich approval payload — PASSED** (2026-04-13, workflow `5799b1d7`). 4 FeedbackRows landed correctly (3 approved + 1 rejected for RISK_SCORE). Three follow-up issues were found during this run and fixed as bundle A/B/C (see §0 below). **This test must be re-run after the fix bundle is committed** to verify the new rich HUMAN_APPROVED details surface correctly in the audit trail and the widened `ApprovalDialog` shows all 4 variable code snippets without truncation.
- ❌ **Tests 1, 3, 4, 5** — NOT YET RUN.

---

## Why this plan exists

Phase 16 shipped long-term memory wiring, HITL API surface (approve-with-feedback / reject / override), frontend HITL dialogs, and runtime ground-truth comparison. Every piece has unit + integration test coverage, but nothing has been exercised end-to-end against the live backend, agentlens proxy, and a real mailbox responder yet. This plan is the gate between "green CI" and "confident in the demo".

---

## §0 — Verify Fix Bundle A/B/C before resuming tests

During Test 2 (2026-04-13 evening), three issues were found and fixed in a follow-up commit bundle on top of Phase 16.5. **Before re-running Test 2 or starting Tests 1/3/4/5, verify all three fixes are present and working.**

### Fix A — Per-step audit events on all step types
**Before:** Only `AgentStepExecutor` emitted `STEP_STARTED`/`STEP_COMPLETED`. `BuiltinStepExecutor`, `ParallelMapStepExecutor`, `GatherStepExecutor`, and `HITLGateStepExecutor` skipped them — so the audit trail of a completed workflow showed only the 1 workflow-level `step_started` + `hitl_gate_waiting` + `human_approved` + auditor's pair.
**After:** All 4 executors now emit `step_started` at entry + `step_completed` at exit (HITLGateStepExecutor emits `step_completed` only on the approve path — reject raises before reaching it, which is the correct semantic). `agent=AgentName.ORCHESTRATOR` for all non-agent step types.
**Verify:** After completing a clinical_derivation workflow end-to-end, `GET /api/v1/workflows/{id}/audit` should return **at least 2 events per step** (one started, one completed) plus the HITL-specific sub-events. For an 8-step pipeline that means ~16+ events total instead of the old 5.
**Smoke check:**
```bash
curl -s http://localhost:8000/api/v1/workflows/<wf_id>/audit | python -c "
import sys, json
events = json.load(sys.stdin)
print(f'total events: {len(events)}')
by_action = {}
for e in events:
    by_action[e['action']] = by_action.get(e['action'], 0) + 1
for action, count in sorted(by_action.items()):
    print(f'  {action}: {count}')
"
```
Expected (happy-path clinical_derivation approve):
- `step_started` ≥ 8 (one per pipeline step + the workflow-level one)
- `step_completed` ≥ 8 (one per pipeline step that didn't raise)
- `hitl_gate_waiting` = 1
- `human_approved` = 1 (now with rich details — see Fix B)

### Fix B — Rich `human_approved` audit details
**Before:** `details = {"gate": "human_review"}`. User-typed reason + per-variable decisions were only visible in the `feedback` table.
**After:** `details` now carries `gate`, `reason`, `approved` (comma-joined variable names), `rejected` (comma-joined variable names), `approved_count`, `rejected_count`. Backwards-compat legacy no-body `/approve` shows `"(legacy no-body approve — all variables)"` for the `approved` field and `"(no reason provided)"` for `reason`.
**Verify:** After the ApprovalDialog approve flow (Test 2), the audit trail's `human_approved` event should have those 6 keys in `details`, populated from the `ApprovalRequest` payload.
**Smoke check:**
```bash
curl -s http://localhost:8000/api/v1/workflows/<wf_id>/audit | python -c "
import sys, json
events = json.load(sys.stdin)
approved = [e for e in events if e['action'] == 'human_approved']
if not approved:
    print('FAIL: no human_approved event')
    sys.exit(1)
print('human_approved details:')
for k, v in approved[0]['details'].items():
    print(f'  {k}: {v!r}')
"
```
Expected shape after an ApprovalDialog approve with RISK_SCORE unchecked and reason "test":
```
gate: 'human_review'
reason: 'test'
approved: 'AGE_GROUP, TREATMENT_DURATION, IS_ELDERLY'
rejected: 'RISK_SCORE'
approved_count: 3
rejected_count: 1
```

### Fix C — ApprovalDialog frame width
**Before:** `sm:max-w-xl` (576px) — code snippets in `VariableApprovalList` truncated mid-expression.
**After:** `sm:max-w-3xl` (768px) in `frontend/src/components/ApprovalDialog.tsx`. The two other dialogs (`RejectDialog`, `CodeEditorDialog`) have their own widths and aren't affected.
**Verify:** Start a workflow, reach the HITL gate, click Approve. The dialog should be wider than before and all 4 variable rows should show their code snippets **without** mid-expression truncation (AGE_GROUP's `pd.cut(df["age"], bins=[0,18,65,200], labels=["minor","adult","senior"], right=F…` should extend further; TREATMENT_DURATION should show more than just `(pd.to_datetime(df["treatment_end"]) - pd.to_datetime(df["treatment_start"])).dt`).

### Fix D — Stale TanStack Query cache for `useWorkflowDag` + `useWorkflowAudit` (FIXED post-fix-bundle)
**Root cause (investigated 2026-04-13 evening):** During Test 2, IS_ELDERLY and RISK_SCORE showed `—` em-dash in the `ApprovalDialog` while AGE_GROUP and TREATMENT_DURATION showed their code correctly. Initial hypothesis blamed the backend, but hitting `GET /api/v1/workflows/5799b1d7/dag` directly via curl showed the backend returns `approved_code` correctly for **all 4 variables** (including the two that appeared as `—`).

The bug was actually in the frontend: `useWorkflowDag` (and `useWorkflowAudit`) were defined with **no `refetchInterval`**, unlike `useWorkflowStatus` which polls every 2 seconds until terminal. The sequence that produced the symptom:

1. User clicks "New Workflow" → `WorkflowDetailPage` mounts → `useWorkflowDag` fires its single fetch **very early** in `derive_variables`, when layer 0 (AGE_GROUP, TREATMENT_DURATION) has derived but layers 1-2 (IS_ELDERLY, RISK_SCORE) have not.
2. The DAG query cache captures that snapshot: 2 variables with code populated + 2 still-pending (`approved_code=null`, `coder_code=null`, `qc_verdict=null`).
3. Workflow progresses through layers 1 and 2 on the backend — but the frontend cache never refetches.
4. User reaches the HITL gate and clicks Approve. `ApprovalDialog` opens with the stale cache.
5. `VariableApprovalList.tsx` renders each row: AGE_GROUP + TREATMENT_DURATION show code + Match badge; IS_ELDERLY + RISK_SCORE show `—` (via the `node.approved_code?.slice(0, 80) ?? node.coder_code?.slice(0, 80) ?? '—'` fallback) and no status badge (because `qc_verdict` is also null in the cached snapshot).

**Same root cause explains an earlier symptom:** the user had to **refresh the page** to see the completed audit trail during Test 2 — that was `useWorkflowAudit` stuck on a stale snapshot from earlier in the run. Both hooks needed the same fix.

**Fix:** Added an `isTerminal: boolean = false` parameter to both `useWorkflowDag` and `useWorkflowAudit`, with `refetchInterval: isTerminal ? false : 2_000`. `WorkflowDetailPage` computes `isTerminal` once from the workflow status and threads it into both hooks. Mirrors the proven pattern used by `useWorkflowStatus`. Stops polling cleanly when the workflow reaches a terminal state.

**Verify:** Open `WorkflowDetailPage` for a workflow still running. Watch the network tab — `GET /workflows/{id}/dag` and `GET /workflows/{id}/audit` should fire every ~2 seconds. Once the workflow reaches `completed` (or `failed`), both requests stop.

**Verify the original symptom is gone:** Run a fresh workflow end-to-end, reach the HITL gate, click Approve. All 4 variables in `ApprovalDialog` must show code snippets (no `—`) and show their QC verdict badges. Also check the Audit tab — it should populate live without needing a manual refresh.

### Fix bundle file inventory
Backend (Fix A + Fix B):
- `src/engine/pipeline_context.py` — 3 new primitive fields (`approval_reason`, `approval_approved_vars`, `approval_rejected_vars`)
- `src/engine/step_executors.py` — `step_started`/`step_completed` emitted by BuiltinStepExecutor, GatherStepExecutor, ParallelMapStepExecutor, HITLGateStepExecutor; HITLGateStepExecutor's HUMAN_APPROVED details enriched
- `src/api/workflow_hitl.py` — `approve_with_feedback_impl` populates the 3 new ctx fields before `event.set()`
- `tests/unit/test_step_executors.py` — updated 2 existing HITL tests, added `test_hitl_gate_without_approval_payload_uses_legacy_fallback`

Frontend (Fix C + Fix D):
- `frontend/src/components/ApprovalDialog.tsx` — `sm:max-w-xl` → `sm:max-w-3xl`
- `frontend/src/hooks/useWorkflows.ts` — `useWorkflowDag` and `useWorkflowAudit` both take `isTerminal` and poll every 2s while not terminal
- `frontend/src/pages/WorkflowDetailPage.tsx` — threads `isTerminal` into `useWorkflowDag` and `useWorkflowAudit`

Tests: backend 298/298 passing (was 297, +1 new legacy-fallback test). Frontend 13/13 still passing (component tests don't assert widths or refetch intervals). pyright/ruff/tsc/eslint clean against the pre-existing baseline.

---

## Prerequisites — stack bring-up

**Four services must run concurrently, one per terminal.**

### Terminal A — AgentLens mailbox proxy
```bash
cd C:\Projects\AgentLens
uv run agentlens serve --mode mailbox --port 8650
```
Leaves agents' LLM calls parked in a mailbox so a responder can feed canned answers back. No real LLM calls in this plan.

### Terminal B — CDDE backend (FastAPI + FastMCP)
```bash
cd C:\Projects\Interviews\jobs\Sanofi-AI-ML-Lead\homework
uv run uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload
```
Health: `curl http://localhost:8000/health` should return `{"status":"ok", "workflows_in_progress":0, ...}`.

### Terminal C — Frontend (Vite React SPA)
```bash
cd C:\Projects\Interviews\jobs\Sanofi-AI-ML-Lead\homework\frontend
npm run dev
```
Open http://localhost:5173 in Chrome. Required for tests 2, 3, 4. Tests 1 and 5 can be driven via scripts + curl.

### Terminal D — Mailbox auto-responder (per test)
One responder at a time. Match the spec:
- **Tests 1, Ground truth:** `PYTHONUNBUFFERED=1 uv run python scripts/mailbox_cdisc.py` (answers `adsl_cdiscpilot01.yaml`, 16 canned responses)
- **Tests 2-5 (UI + LTM):** `PYTHONUNBUFFERED=1 uv run python scripts/mailbox_simple_mock.py` (answers `simple_mock.yaml`, 10 canned responses)

Responder exits cleanly after 30 min idle — fine to leave running between tests if they use the same spec.

### Baseline DB snapshot (captures starting row counts for test 5)
Before starting Test 1, capture the current state of the LTM tables so Test 5 can verify a delta:
```bash
cd C:\Projects\Interviews\jobs\Sanofi-AI-ML-Lead\homework
uv run python -c "
import asyncio
from src.persistence.database import init_db
from src.persistence.pattern_repo import PatternRepository
from src.persistence.qc_history_repo import QCHistoryRepository

async def main():
    sf = await init_db('sqlite+aiosqlite:///cdde.db')
    async with sf() as s:
        pr = PatternRepository(s)
        qc = QCHistoryRepository(s)
        for v in ['AGE_GROUP', 'TREATMENT_DURATION', 'IS_ELDERLY', 'RISK_SCORE']:
            rows = await pr.query_by_type(v, limit=100)
            print(f'patterns[{v}]={len(rows)}')
        stats = await qc.get_stats()
        print(f'qc_history total={stats.total}')

asyncio.run(main())
"
```
Write the output down. You'll compare against it in Test 5.

---

## §0.5 — Mailbox protocol (manual responder, no auto-responder)

If you run the tests with the **auto-responder scripts** (`scripts/mailbox_simple_mock.py` or `scripts/mailbox_cdisc.py`), skip this section. If you want Anima (or any other manual driver) to feed canned responses into the AgentLens mailbox one by one, this is the reference protocol.

### Base URL
```
http://localhost:8650/mailbox
```

### Poll for pending requests
```bash
curl -s http://localhost:8650/mailbox | python -m json.tool
```
Returns a JSON array. Each entry has `request_id`, `model`, `preview` (first N chars of the user message), and `age_seconds`. Empty array `[]` = no pending requests.

### Inspect a specific request
```bash
curl -s http://localhost:8650/mailbox/{rid} | python -m json.tool | head -60
```
Returns `messages[0]` (system prompt — check for `"QC"` keyword to identify coder vs QC role, or `"debugger"` / `"audit"` keywords for other agents) and `messages[1]` (user prompt — check for the variable name or "Debug mismatch"/"Generate audit summary" keywords).

### Quick role identification helper
```bash
for rid in $(curl -s http://localhost:8650/mailbox | python -c "import sys,json; print(' '.join(str(e['request_id']) for e in json.load(sys.stdin)))"); do
  role=$(curl -s http://localhost:8650/mailbox/$rid | python -c "
import sys, json
d = json.load(sys.stdin)
sysmsg = d['messages'][0]['content']
if 'debugger' in sysmsg.lower(): print('DEBUGGER')
elif 'audit' in sysmsg.lower(): print('AUDITOR')
elif 'QC' in sysmsg or 'independent' in sysmsg.lower(): print('QC')
else: print('CODER')
")
  preview=$(curl -s http://localhost:8650/mailbox/$rid | python -c "import sys,json; print(json.load(sys.stdin)['messages'][1]['content'][:60])")
  echo "#$rid $role — $preview"
done
```

### Respond — curl template (simple cases)
```bash
curl -s -X POST http://localhost:8650/mailbox/{rid} \
  -H "Content-Type: application/json" \
  -d '{"content":"","tool_calls":[{"id":"call_{rid}","type":"function","function":{"name":"final_result","arguments":"{\"variable_name\":\"X\",\"python_code\":\"...\",\"approach\":\"...\",\"null_handling\":\"...\"}"}}]}'
```

**WARNING — bash curl with -d breaks on complex python_code strings.** During Test 2 the response for `{"senior": True, "adult": False, "minor": False}` failed with `{"detail":"There was an error parsing the body"}` because bash eats the escaping on dict-literal + boolean sequences. The fix is to use Python urllib.request with `json.dumps()` for anything beyond the most trivial string values — next section.

### Respond — Python helper (use this for anything non-trivial)
```bash
python -c "
import json, urllib.request
rid = 6  # CHANGE ME
args = {
    'variable_name': 'IS_ELDERLY',
    'python_code': 'df[\"AGE_GROUP\"].map({\"senior\": True, \"adult\": False, \"minor\": False})',
    'approach': 'Dictionary mapping',
    'null_handling': 'NaN keys map to NaN automatically'
}
body = json.dumps({
    'content': '',
    'tool_calls': [{
        'id': f'call_{rid}',
        'type': 'function',
        'function': {'name': 'final_result', 'arguments': json.dumps(args)}
    }]
}).encode()
req = urllib.request.Request(f'http://localhost:8650/mailbox/{rid}', data=body, method='POST')
req.add_header('Content-Type', 'application/json')
print(urllib.request.urlopen(req).read().decode())
"
```
Successful POST returns `{"status":"submitted"}`.

### Canned response library for `simple_mock.yaml`

**9 or 10 mailbox requests total for one clinical_derivation run** (4 for layer 0 + 2 for layer 1 + 2 for layer 2 + optional debugger + 1 auditor).

| # | Layer / role | Variable | Response — `python_code` field |
|---|---|---|---|
| N | Coder | `AGE_GROUP` | `pd.cut(df["age"], bins=[0,18,65,200], labels=["minor","adult","senior"], right=False)` |
| N | QC | `AGE_GROUP` | `pd.Series(np.select([df["age"]<18, df["age"]<65, df["age"]>=65], ["minor","adult","senior"], default=None), index=df.index).where(df["age"].notna())` |
| N | Coder | `TREATMENT_DURATION` | `(pd.to_datetime(df["treatment_end"]) - pd.to_datetime(df["treatment_start"])).dt.days + 1` |
| N | QC | `TREATMENT_DURATION` | `df.apply(lambda r: (pd.to_datetime(r["treatment_end"]) - pd.to_datetime(r["treatment_start"])).days + 1 if pd.notna(r["treatment_end"]) and pd.notna(r["treatment_start"]) else None, axis=1).astype("Float64")` |
| N | Coder | `IS_ELDERLY` | `(df["AGE_GROUP"] == "senior").where(df["AGE_GROUP"].notna())` |
| N | QC | `IS_ELDERLY` | `df["AGE_GROUP"].map({"senior": True, "adult": False, "minor": False})` |
| N | Coder | `RISK_SCORE` | `pd.Series(np.select([df["IS_ELDERLY"].eq(True) & df["TREATMENT_DURATION"].gt(120), df["IS_ELDERLY"].eq(True) & df["TREATMENT_DURATION"].le(120), df["IS_ELDERLY"].eq(False)], ["high", "medium", "low"], default=None), index=df.index).where(df["IS_ELDERLY"].notna() & df["TREATMENT_DURATION"].notna(), other=None)` |
| N | QC | `RISK_SCORE` | `df.apply(lambda r: ("high" if r["TREATMENT_DURATION"] > 120 else "medium") if r["IS_ELDERLY"] == True else "low" if pd.notna(r["IS_ELDERLY"]) and pd.notna(r["TREATMENT_DURATION"]) else None, axis=1)` |

**Debugger** (appears conditionally — RISK_SCORE triggers a QC mismatch on the two null-handling approaches above):
```json
{
  "variable_name": "RISK_SCORE",
  "root_cause": "Null-handling difference between np.select default and apply None return — edge case on missing IS_ELDERLY",
  "correct_implementation": "qc",
  "suggested_fix": "df.apply(lambda r: (\"high\" if r[\"TREATMENT_DURATION\"] > 120 else \"medium\") if r[\"IS_ELDERLY\"] == True else \"low\" if pd.notna(r[\"IS_ELDERLY\"]) and pd.notna(r[\"TREATMENT_DURATION\"]) else None, axis=1)",
  "confidence": "high"
}
```

**Auditor** (fires after HITL gate is approved — must respond or the workflow hangs at `audit` forever):
```json
{
  "study": "simple_mock",
  "total_derivations": 4,
  "auto_approved": 3,
  "qc_mismatches": 1,
  "human_interventions": 1,
  "summary": "All 4 derivations completed. AGE_GROUP, TREATMENT_DURATION, and IS_ELDERLY passed QC on first attempt. RISK_SCORE had a QC mismatch resolved by the debugger in favor of the QC implementation. Human reviewer approved with per-variable feedback.",
  "recommendations": [
    "Review RISK_SCORE null handling edge case for production robustness",
    "Consider adding explicit null-propagation unit tests for multi-source derivations"
  ]
}
```

### Canned response library for `adsl_cdiscpilot01.yaml`
**16 mailbox requests total** (7 ADSL variables × 2 roles coder/QC, plus possibly debugger + auditor). The full set is in `scripts/mailbox_cdisc.py::RESPONSES` — read that file and copy the `python_code` values into curl/Python responses the same way. The 7 variables are: `AGEGR1`, `TRTDUR`, `SAFFL`, `ITTFL`, `EFFFL`, `DISCONFL`, `DURDIS`. The spec file is `specs/adsl_cdiscpilot01.yaml`.

### Per-test manual-driver workflow

**Test 1 (ground truth against CDISC):** Use the full `adsl_cdiscpilot01.yaml` canned library above (16+ responses). Respond to all coder/QC/debugger/auditor requests in sequence. After the workflow reaches `human_review`, curl `POST /workflows/{id}/approve` with no body (backwards-compat legacy path — you're not testing the HITL dialogs here, just the ground truth endpoint). After completion, hit `GET /workflows/{id}/ground_truth` and verify the report.

**Test 2 (rich approval via UI):** Use the `simple_mock.yaml` library above. Respond to the 8 (or 9 with debugger) coder/QC requests. When the workflow reaches `human_review`, **stop responding and hand off to the UI driver**. The UI driver opens `ApprovalDialog`, unchecks one variable (suggested: RISK_SCORE), types a reason, and clicks Approve. Then the auditor request arrives in the mailbox — respond to it to let the workflow complete.

**Test 3 (reject via UI):** Same pattern as Test 2 up to the HITL gate. When it reaches `human_review`, the UI driver opens `RejectDialog`, types a mandatory reason, and clicks Confirm Rejection. **No auditor request will appear** — the workflow fails cleanly via `WorkflowRejectedError` without running the audit step. Check the backend logs to confirm no `CancelledError` was raised.

**Test 4 (override via UI):** Same pattern as Test 2 up to the HITL gate. When it reaches `human_review`, the UI driver opens `CodeEditorDialog` on a variable, edits the code, and saves. The override endpoint re-executes the new code locally (no mailbox request). After the override succeeds, the UI driver then approves the gate normally. The auditor request arrives in the mailbox — respond to it.

**Test 5 (LTM cross-run):** Run the `simple_mock.yaml` workflow twice in a row. Responses for each run are the same 9 mailbox turns (it's deterministic). Before each run, capture a baseline snapshot of the `patterns` + `qc_history` tables. After each run completes, re-snapshot and verify the delta is exactly +1 row per variable in `patterns` + +4 rows in `qc_history`.

### Mailbox protocol gotchas observed in Test 2
1. **Bash curl escapes break on dict literals with booleans** — the `{"senior": True, ...}` response for IS_ELDERLY failed via curl -d because bash ate some escaping. **Fix:** use Python urllib.request + json.dumps for any response whose `python_code` has more than trivial string values.
2. **`workflows_in_progress` on `/health` may leak** — during Test 2 the counter showed 1 before we even started, probably from an earlier test that didn't decrement on terminal state. Non-blocking but worth tracking; `WorkflowManager._running` isn't being cleaned up on all terminal paths.
3. **`curl GET /mailbox/{rid}`** may return messages lists with any length — always guard with `if len(d['messages']) > 1` before accessing `messages[1]`.
4. **Auditor is the final mailbox turn** — once you respond to it, the workflow races through `save_patterns → audit → export → completed` in about 1-2 seconds. Be ready to query the DB / audit API immediately for verification.

---

## Test 1 — Ground truth endpoint (Phase 16.4)

**What this tests:** The new `compare_ground_truth` builtin runs inside the `clinical_derivation` pipeline between `derive_variables` and `human_review`, compares the derived DataFrame against the reference CDISC ADSL XPT file via an inner-join on `USUBJID`, and the `GET /workflows/{id}/ground_truth` endpoint returns the report.

### Setup
- Responder: `mailbox_cdisc.py` (Terminal D)
- Spec: `specs/adsl_cdiscpilot01.yaml`

### Steps
1. **Terminal E — kick off the workflow via MCP driver:**
   ```bash
   cd C:\Projects\Interviews\jobs\Sanofi-AI-ML-Lead\homework
   uv run python scripts/mcp_run_cdisc.py
   ```
   This drives the pipeline through MCP, prints per-poll status until it parks at the HITL gate. Note the `wf_id=<8char>` it prints.

2. **Wait for `api_fsm=human_review`** in the poll log. This means:
   - `parse_spec` ✅
   - `build_dag` ✅
   - `derive_variables` ✅ (7 ADSL derivations done; mailbox responder fed all 14 coder+QC canned answers)
   - `ground_truth_check` ✅ ← **the new step ran and `ctx.ground_truth_report` should now be populated**
   - `human_review` ⏸

3. **Before approving, hit the new endpoint:**
   ```bash
   curl -s http://localhost:8000/api/v1/workflows/<wf_id>/ground_truth | python -m json.tool
   ```

4. **Expected response:**
   - HTTP 200
   - `ground_truth_path` ends with `data/adam/cdiscpilot01/adsl.xpt`
   - `total_variables == 7` (all declared ADSL derivations)
   - `matched_variables >= 1` (AGEGR1 at minimum — the CDISC pilot reference)
   - `results` is a list of 7 `VariableGroundTruthResult` entries
   - At least one result has `verdict == "match"` with `match_count > 0`

5. **Negative path — premature call:** Start *another* workflow, and **before** it reaches `ground_truth_check`, hit `/ground_truth`. **Expected:** HTTP 404 with detail `"Ground truth check has not been run for this workflow"`.

6. **Approve the original workflow** (curl `POST /workflows/<wf_id>/approve`, no body — backwards-compat path) and verify it completes cleanly through `audit` → `export` → `completed`.

### Things to watch for
- **Dtype surprises:** `pyreadstat` returns `object` dtype for categorical XPT columns. The integration test handles this via `.astype(str)` on both sides. If the endpoint returns `verdict="mismatch"` for AGEGR1 in production, the bug is here.
- **Suffix collision guard:** `_load_and_align_gt` returns `frozenset(gt_df.columns)` to avoid spurious MATCH on variables missing from the ground truth. If an unknown variable ends up with `verdict="match"` instead of an `error` field, the guard regressed.
- **Primary key alignment:** The builtin inner-joins on `spec.source.primary_key` (USUBJID for CDISC). If the derived frame and the ground-truth frame don't share any USUBJIDs, `aligned` is empty and every result has `total_rows=0`. Unlikely but flag it.

### Pass criteria
- [ ] Endpoint returns 200 after step runs
- [ ] Endpoint returns 404 before step runs
- [ ] AGEGR1 verdict is `match` with non-zero `match_count`
- [ ] No backend errors in the log during `ground_truth_check` execution

---

## Test 2 — Rich approval payload via the UI (Phase 16.2b + 16.3b)

**What this tests:** The `POST /approve` endpoint accepts an optional `ApprovalRequest` body with per-variable decisions, persists one `FeedbackRow` per decision, and backwards-compat still works for callers that pass no body. Frontend `ApprovalDialog` constructs the payload correctly.

### Setup
- Responder: `mailbox_simple_mock.py` (Terminal D)
- Spec: `specs/simple_mock.yaml` (4 variables: AGE_GROUP, TREATMENT_DURATION, IS_ELDERLY, RISK_SCORE)
- Frontend: http://localhost:5173 open in Chrome

### Steps
1. **In the UI:** click "New Workflow" on the dashboard. Pick `simple_mock.yaml`. Click Start.
2. **Wait for the amber HITL banner** — `status.awaiting_approval === true`. You should see the new pair of buttons: **Approve** (emerald) and **Reject** (red outline). The DAG tab should show all 4 variables with `status=approved`.
3. **Click Approve.** `ApprovalDialog` opens.
4. **Verify default state:** All 4 variables have their checkboxes ticked (approve-all default). Variable names + QC verdict badges + code snippets visible. A reason textarea at the bottom (optional).
5. **Uncheck one variable** — e.g., uncheck `RISK_SCORE`.
6. **Type a reason** in the textarea: `RISK_SCORE needs a different tolerance`.
7. **Click "Approve & Run Audit".** Dialog closes, workflow advances to `save_patterns` → `audit` → `export` → `completed`.
8. **Query the feedback table** to verify the per-variable rows:
   ```bash
   cd C:\Projects\Interviews\jobs\Sanofi-AI-ML-Lead\homework
   uv run python -c "
   import asyncio
   from src.persistence.database import init_db
   from sqlalchemy import select
   from src.persistence.orm_models import FeedbackRow

   async def main():
       sf = await init_db('sqlite+aiosqlite:///cdde.db')
       async with sf() as s:
           result = await s.execute(select(FeedbackRow).order_by(FeedbackRow.id.desc()).limit(10))
           for row in result.scalars():
               print(f'{row.id}: variable={row.variable!r} action={row.action_taken!r} feedback={row.feedback!r}')

   asyncio.run(main())
   "
   ```

### Expected
- **4 new FeedbackRows** — one per VariableDecision.
- AGE_GROUP, TREATMENT_DURATION, IS_ELDERLY each have `action_taken='approved'`, feedback empty or the reason text (per the ApprovalDialog logic: note defaults to null, reason fallback).
- RISK_SCORE has `action_taken='rejected'` (since it was unchecked).
- All 4 rows have `study='simple_mock'` (or whatever the spec declares).

### Backwards-compat sub-test (curl)
Also verify the no-body path still works:
```bash
# Start another workflow via curl
curl -s -X POST http://localhost:8000/api/v1/workflows/ \
  -H "Content-Type: application/json" \
  -d '{"spec_path":"specs/simple_mock.yaml"}'
# Poll status, wait for human_review, then:
curl -s -X POST http://localhost:8000/api/v1/workflows/<wf_id>/approve
```
**Expected:** 200 response with the workflow status. The workflow should advance normally. No FeedbackRows are written (empty payload short-circuits the write path in `approve_with_feedback`). This is the behavior existing callers rely on.

### Pass criteria
- [ ] ApprovalDialog opens with approve-all default
- [ ] Unchecking a variable sends `approved=false` for that variable
- [ ] Reason textarea contents are persisted
- [ ] Exactly 4 FeedbackRows per run, correctly split by action_taken
- [ ] No-body curl path still releases the gate cleanly (backwards compat)

---

## Test 3 — Reject path via the UI (Phase 16.2a + 16.2b + 16.3b)

**What this tests:** The critical rejection flow. FSM must reach `failed` cleanly via `WorkflowRejectedError` (inheriting `Exception`), NOT via `task.cancel()` (which raises `CancelledError`, a `BaseException` that would leak the task).

### Setup
- Same as Test 2 (`simple_mock.yaml` + mailbox + frontend)

### Steps
1. Start a fresh workflow from the UI.
2. Wait for the HITL banner.
3. **Click Reject.** `RejectDialog` opens.
4. **Verify empty-reason guard:** Try clicking "Confirm Rejection" with an empty textarea. The button must be disabled. Also try typing only spaces — still disabled (whitespace trim).
5. **Type a reason:** `QC mismatch unresolved — debugger could not fix`.
6. **Click "Confirm Rejection".** Dialog closes. Observe the workflow status transition.
7. **Verify FSM state:** refresh the dashboard or click back to Dashboard. The workflow card should show `status=failed` (or similar terminal-fail state). NOT stuck in `human_review`. NOT stuck in `rejecting`. Clean transition.
8. **Backend log inspection:** In Terminal B (backend uvicorn output), look for:
   - `HITL gate waiting` event (from when the step parked)
   - `Workflow rejected by human` audit record (the `HUMAN_REJECTED` action)
   - `Workflow <wf_id> failed` from `_run_and_cleanup`'s `except Exception` — this is the critical path, confirms the exception bubbled up correctly
   - **NOT** `CancelledError` or `Task was cancelled` anywhere in the log for this workflow
9. **Verify no leaked task:** Hit `GET /health`. `workflows_in_progress` should reflect the fact that the workflow is terminated (not stuck counting as in-progress).
10. **Verify the FeedbackRow:**
    ```bash
    uv run python -c "
    import asyncio
    from src.persistence.database import init_db
    from sqlalchemy import select
    from src.persistence.orm_models import FeedbackRow

    async def main():
        sf = await init_db('sqlite+aiosqlite:///cdde.db')
        async with sf() as s:
            result = await s.execute(
                select(FeedbackRow).where(FeedbackRow.action_taken == 'rejected').order_by(FeedbackRow.id.desc()).limit(3)
            )
            for row in result.scalars():
                print(f'{row.id}: feedback={row.feedback!r}')

    asyncio.run(main())
    "
    ```
    **Expected:** the most recent `rejected` row has the exact reason text you typed.

### Negative path — 422 on empty reason (curl)
Direct API test to verify `Field(min_length=1)` validation:
```bash
curl -s -X POST http://localhost:8000/api/v1/workflows/<wf_id>/reject \
  -H "Content-Type: application/json" \
  -d '{"reason":""}' | python -m json.tool
```
**Expected:** HTTP 422, Pydantic validation error about `reason` being too short.

### Negative path — 409 on already-completed workflow
After the workflow has reached a terminal state, try rejecting it again:
```bash
curl -s -X POST http://localhost:8000/api/v1/workflows/<wf_id>/reject \
  -H "Content-Type: application/json" \
  -d '{"reason":"too late"}' | python -m json.tool
```
**Expected:** HTTP 409 (not at the HITL gate anymore).

### Pass criteria
- [ ] RejectDialog disables Confirm on empty/whitespace-only reason
- [ ] FSM reaches `failed` cleanly after reject
- [ ] No `CancelledError` / `Task was cancelled` in backend logs
- [ ] `workflows_in_progress` drops by 1 after the reject
- [ ] FeedbackRow with `action_taken='rejected'` and correct reason text
- [ ] Empty-reason curl returns 422
- [ ] Post-terminal reject returns 409

---

## Test 4 — Variable override via CodeEditorDialog (Phase 16.2b + 16.3b)

**What this tests:** `OverrideService.override_variable` runs the new code via `execute_derivation`, applies the resulting Series to `ctx.derived_df` only on success, updates `node.approved_code`, records `HUMAN_OVERRIDE` audit, writes feedback, commits once. Error paths preserve the original state.

### Setup
- Same as Test 2

### Happy path
1. Start a fresh workflow. Wait for the HITL gate.
2. Open the Code tab in the UI (or navigate to the variable list — depends on the current tab ordering).
3. **Verify Edit button visibility:** Each variable card should have an outline "Edit" button next to the variable name/badge. This button must ONLY appear when `status.awaiting_approval === true`.
4. **Click Edit on `AGE_GROUP`.** `CodeEditorDialog` opens with the current `approved_code` pre-filled in a monospace `rows={20}` textarea.
5. **Modify the code** to something equivalent but syntactically different:
   - Original (from mailbox_simple_mock canned response): `pd.cut(df['age'], bins=[0,18,65,200], labels=['minor','adult','senior'])`
   - Override candidate: `pd.Series(np.select([df['age'] < 18, df['age'] < 65], ['minor', 'adult'], default='senior'), index=df.index)`
   - (Make sure the second form is semantically equivalent — otherwise `execute_derivation` will run fine but the derived column will look different to the auditor.)
6. **Type a reason:** `Prefer np.select for readability`.
7. **Verify save-button guards:** the Save button should be disabled when (a) code unchanged from currentCode, (b) reason empty, (c) mutation is in-flight.
8. **Click Save Override.** Dialog closes (mutation `onSuccess` callback).
9. **Verify DAG update:** Refresh the DAG view. The AGE_GROUP node's `approved_code` should show the new code, not the original.
10. **Verify audit event:** Open the Audit tab. There should be a new `HUMAN_OVERRIDE` audit record with `details.reason` = your reason text and `details.variable = "AGE_GROUP"`.
11. **Verify the FeedbackRow:** Query:
    ```bash
    uv run python -c "
    import asyncio
    from src.persistence.database import init_db
    from sqlalchemy import select
    from src.persistence.orm_models import FeedbackRow

    async def main():
        sf = await init_db('sqlite+aiosqlite:///cdde.db')
        async with sf() as s:
            result = await s.execute(
                select(FeedbackRow).where(FeedbackRow.action_taken == 'overridden').order_by(FeedbackRow.id.desc()).limit(3)
            )
            for row in result.scalars():
                print(f'{row.id}: variable={row.variable!r} feedback={row.feedback!r}')

    asyncio.run(main())
    "
    ```
    **Expected:** new row with `variable='AGE_GROUP'`, `action_taken='overridden'`, `feedback=<your reason>`.

### Error path — syntax-broken code (400)
12. **Click Edit again** on the same or another variable.
13. **Paste syntax-broken code:** `df[['AGE_GROUP'` (missing closing bracket).
14. **Type a reason** (the field is still mandatory).
15. **Click Save Override.**
16. **Expected:** Save button briefly shows "Saving..." then the dialog shows an inline error banner (red, with AlertCircle icon) containing the error message from the 400 response. The original `approved_code` must NOT have been mutated — close the dialog, reopen it, verify `currentCode` is still the pre-override value.

### Error path — unknown variable (404)
17. Direct API test:
    ```bash
    curl -s -X POST http://localhost:8000/api/v1/workflows/<wf_id>/variables/PHANTOM_VAR/override \
      -H "Content-Type: application/json" \
      -d '{"new_code":"df[\"age\"]","reason":"test"}' | python -m json.tool
    ```
    **Expected:** HTTP 404 with detail like `"variable 'PHANTOM_VAR' not found"`.

### Pass criteria
- [ ] Edit button only visible when `awaiting_approval === true`
- [ ] CodeEditorDialog pre-fills `currentCode`
- [ ] Save disabled on unchanged code
- [ ] Save disabled on empty reason
- [ ] Save disabled while mutation pending
- [ ] Happy path updates `node.approved_code` in the DAG view
- [ ] Happy path records `HUMAN_OVERRIDE` audit event
- [ ] Happy path writes a FeedbackRow with `action_taken='overridden'`
- [ ] 400 path shows inline error and preserves original code
- [ ] 404 path returns on unknown variable

---

## Test 5 — Long-term memory cross-run spot check (Phase 16.1)

**What this tests:** The LTM loop still works after all the 16.2-16.5 changes haven't regressed it. Running `simple_mock.yaml` twice should produce +1 pattern row and +1 qc_history row per approved variable per run. The coder agent's second run should observe the first run's patterns via `query_patterns`.

### Setup
- Same as Test 2
- **Capture the baseline** (using the snapshot script from the Prerequisites section). Write the numbers down.

### Steps
1. **Run 1:** start a workflow via the UI (or `scripts/mcp_test_checkpoint.py` if you want the checkpoint-timeline report). Approve with all variables approved (or use curl `POST /approve` with no body). Wait for `status=completed`.
2. **Snapshot the tables** (run the snapshot script from Prerequisites again). You should see:
   - `patterns[AGE_GROUP] = baseline + 1`
   - `patterns[TREATMENT_DURATION] = baseline + 1`
   - `patterns[IS_ELDERLY] = baseline + 1`
   - `patterns[RISK_SCORE] = baseline + 1`
   - `qc_history.total = baseline + 4`
3. **Run 2:** start a second workflow with the same spec. While it's running, watch Terminal A (AgentLens) for `query_patterns` tool calls — the coder agent should invoke it at least once per variable before generating code.
4. **Approve run 2** and wait for completion.
5. **Snapshot the tables a third time.** Expected deltas from the original baseline:
   - `patterns[AGE_GROUP] = baseline + 2`
   - `patterns[TREATMENT_DURATION] = baseline + 2`
   - `patterns[IS_ELDERLY] = baseline + 2`
   - `patterns[RISK_SCORE] = baseline + 2`
   - `qc_history.total = baseline + 8`

### Advanced check — verify `query_patterns` tool actually observed the first run's rows
Inspect the AgentLens trajectory for run 2. The coder's tool-call log should include a `query_patterns` call for each variable, and the returned string should contain `=== PATTERN N (study=simple_mock, approach=...) ===` blocks with code snippets from run 1.

Alternative: manually invoke the tool via a Python one-liner to verify the repo returns what we expect:
```bash
uv run python -c "
import asyncio
from src.persistence.database import init_db
from src.persistence.pattern_repo import PatternRepository

async def main():
    sf = await init_db('sqlite+aiosqlite:///cdde.db')
    async with sf() as s:
        repo = PatternRepository(s)
        for v in ['AGE_GROUP', 'TREATMENT_DURATION', 'IS_ELDERLY', 'RISK_SCORE']:
            rows = await repo.query_by_type(v, limit=3)
            print(f'=== {v} ({len(rows)} rows) ===')
            for r in rows:
                print(f'  study={r.study} approach={r.approach!r} code={r.approved_code[:60]}...')

asyncio.run(main())
"
```
**Expected:** 3 rows per variable (the tool's `limit=3` cap), with distinct `approach` labels proving they came from different runs.

### Pass criteria
- [ ] Run 1 produces exactly +1 pattern row and +1 qc_history row per variable
- [ ] Run 2 produces exactly another +1 pattern row and +1 qc_history row per variable
- [ ] AgentLens trace shows `query_patterns` tool calls in run 2
- [ ] Direct `PatternRepository.query_by_type` returns rows from multiple runs

---

## Summary — passing this plan

All 5 tests pass = Phase 16 is ready for the interview demo. A single failure in test 3 (rejection path leaking a task) or test 4 (override error path corrupting state) is a blocker. Tests 1, 2, and 5 are confidence checks — failures there suggest the build is broken but recoverable.

### After passing
1. Archive this file — move to `docs/` or add a "passed YYYY-MM-DD" note at the top.
2. Update `IMPLEMENTATION_STATUS.md` with the test results.
3. Proceed to the demo prep: slides, design.docx review, walkthrough rehearsal.

### If any test fails
1. Capture backend log output + the failing step + the actual vs expected row in the DB
2. Open an issue in the project or flag it here under a new "## Known failures" section
3. Fix-forward via a targeted commit on `feat/yaml-pipeline`
4. Re-run the affected test + run the full tooling gate (`pytest`, `lint-imports`, pre-push hooks)
