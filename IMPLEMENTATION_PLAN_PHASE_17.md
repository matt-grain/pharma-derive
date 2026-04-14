# Phase 17 — Bug Fix Release Plan (Bugs #1–#5)

**Date:** 2026-04-13
**Source of truth:** `BUGS.md` (5 bugs surfaced during Phase 16 manual testing)
**Branch:** `feat/yaml-pipeline` (commit Phase 16.6 + docs first, then Phase 17 plan files; if a clean isolation is desired later, branch `feat/phase17-bug-fixes` from HEAD)
**Total phases:** 3 (sequenced by risk + dependency, not by bug number)
**Total commits expected:** 5 (1 per phase + 1 fix bundle + 1 docs commit pre-Phase-17)

---

## Phase summary table

| Phase | Title | Bugs | Files (new + modified) | Agent | Depends on |
|---|---|---|---|---|---|
| **17.1** | LTM read loop expansion (2 new tools, repo methods, agent wiring) | **#5** | 7 new + 6 modified | `python-fastapi` | None |
| **17.2** | Per-variable audit emission inside derivation_runner | **#1** | 1 new + 4 modified | `python-fastapi` | None (independent of 17.1) |
| **17.3** | Cleanup bundle: 404 disambiguation + asyncio task warning + dialog state leak | **#2 #3 #4** | 0 new + 5 modified (3 backend + 2 frontend) | `python-fastapi` (3 backend) → `vite-react` (2 frontend) | None |

**No cross-phase dependencies.** Phases can run in parallel if Matt wants to dispatch them concurrently — they touch disjoint files. Recommended sequencing for review clarity: 17.1 → 17.2 → 17.3 (largest architectural change first, smallest cleanups last).

---

## Why this sequencing

Per the /plan-release prompt: *"Sequence the bugs by dependency and risk: Bug #5 and Bug #1 are the load-bearing items; #2 #3 #4 are smaller cleanups."*

- **Phase 17.1 (Bug #5)** is the architectural centerpiece. It expands the LTM read surface from 1 tool to 3, touches the agent registry, the coder YAML config, two persistence repositories, the `CoderDeps` dataclass, the factory wiring, and adds a brand-new test file. Highest risk of regression in the agent reasoning loop. Goes first so the next phases land on a stable base.
- **Phase 17.2 (Bug #1)** adds per-variable audit emission inside `derivation_runner.run_variable`. Touches one new `AuditAction` enum value + the runner itself + 1-2 unit tests. Independent of 17.1 in code, but runs second so the new audit events are visible in the same demo as the new LTM tools (and so any audit-trail debugging from 17.1 doesn't need to be redone after 17.2 lands).
- **Phase 17.3 (Bugs #2, #3, #4)** is three small, independent cleanups bundled together because each is too small to justify its own phase. Two are backend Python changes (workflows.py router, workflow_manager.py exception handling); one is a frontend TypeScript change (parent component's onOpenChange handler). The backend changes go first under `python-fastapi`, then the frontend cleanup under `vite-react`.

---

## Cross-phase dependencies

**None.** Each phase touches disjoint files. The only shared code path is the audit trail (Phase 17.2 adds events that Phase 17.1's tools may eventually surface, but neither depends on the other compiling first).

If Matt wants belt-and-suspenders, run 17.1 → tooling gate → 17.2 → tooling gate → 17.3 → tooling gate → final integration test pass. If he wants to ship faster, all three can be dispatched in parallel since they touch disjoint files.

---

## Tooling gate (run after EVERY phase)

```bash
cd C:\Projects\Interviews\jobs\Sanofi-AI-ML-Lead\homework
uv run pyright .
uv run ruff check . --fix
uv run ruff format .
uv run lint-imports
uv run pytest tests/ -q
```

If any phase touches frontend files (only Phase 17.3):
```bash
cd C:\Projects\Interviews\jobs\Sanofi-AI-ML-Lead\homework\frontend
npx tsc -b --noEmit   # frontend has NO 'typecheck' script — use this instead
npm run lint
npm run test
```

After ALL three phases, run the full pre-push hook gate:
```bash
cd C:\Projects\Interviews\jobs\Sanofi-AI-ML-Lead\homework
.git/hooks/pre-push  # or: uv run pre-commit run --hook-stage pre-push --all-files
```
All 18 pre-push hooks must be green (matches the Phase 16 baseline).

---

## Acceptance criteria — Phase 17 release as a whole

A Phase 17 release is "done" when ALL of the following hold:

1. **All 5 bugs from BUGS.md have a closing entry** noting the fix commit SHA and date.
2. **Test suite total:** ≥ 311 backend tests passing (current baseline from Phase 16) + new tests added in 17.1 (≥ 8) and 17.2 (≥ 2). Target: ≥ 321 passing.
3. **Frontend:** 13 component tests passing (current baseline) + new test added in 17.3 (≥ 1). Target: ≥ 14 passing.
4. **Tooling gate:** all 18 pre-push hooks green on the final commit.
5. **Manual verification:** re-run TEST_PLAN_P16.md Test 2 + Test 3 + Test 4 against the post-Phase-17 build. Each test should produce the same assertions as in Phase 16 plus the new visible improvements:
   - **Test 2 (rich approval):** audit trail now shows per-variable `coder_proposed`/`qc_verdict` events with the variable column populated (Bug #1 closed)
   - **Test 3 (reject):** backend log shows NO "Task exception was never retrieved" warning (Bug #3 closed)
   - **Test 4 (override):** trigger the 400 syntax error path, close + reopen the dialog → no stale error banner (Bug #4 closed); `/api/v1/workflows/<wf>/ground_truth` returns the disambiguated 404 message for simple_mock (Bug #2 closed)
6. **LTM smoke check (Bug #5):** run two simple_mock workflows back-to-back. Inspect AgentLens trajectory for Run 2's coder calls (or a `FunctionModel` test if mailbox-mode hides the calls — see REFACTORING.md F17/F18). Confirm the new `query_feedback` and `query_qc_history` tools are wired into the coder agent's tool registry.

---

## Per-phase plan files (read these before dispatching)

- `IMPLEMENTATION_PLAN_PHASE_17_1.md` — Bug #5 detailed specs (LTM read loop)
- `IMPLEMENTATION_PLAN_PHASE_17_2.md` — Bug #1 detailed specs (per-variable audit)
- `IMPLEMENTATION_PLAN_PHASE_17_3.md` — Bugs #2 #3 #4 detailed specs (cleanup bundle)

Each per-phase file is self-contained: a subagent reading ONLY that file has every spec it needs. The overview file (this one) only contains sequencing and acceptance criteria — never per-file implementation specs.

---

## Dispatch instructions for the orchestrator

For each phase, dispatch via `Task` with `subagent_type=python-fastapi` (or `vite-react` for the frontend portion of 17.3). The subagent prompt MUST include:

1. The full per-file spec from the corresponding `IMPLEMENTATION_PLAN_PHASE_17_<N>.md` file
2. The "AFTER IMPLEMENTING" tooling block from `/plan-release` step 3b
3. The constraint set matching the project type (FastAPI strict typing, layered architecture, ruff + pyright + import-linter)

After each phase completes, the orchestrator must:
1. Glob the expected files to verify creation
2. Run the tooling gate
3. Spot-read 1-2 files to verify they follow project patterns
4. Update task status before dispatching the next phase

---

## Workaround during Phase 17 development

The Phase 16 manual test session (Tests 2-5) PASSED with the current Fix Bundle A/B/C/D in the working tree. Phase 17 must NOT regress those tests. The recommended development loop:

1. Implement phase
2. Run tooling gate
3. Re-run the manual test that exercises the bug being fixed (e.g. for 17.2, re-run Test 2 and verify per-variable events appear)
4. Commit the phase
5. Move to next phase

This catches regressions immediately instead of discovering them at the final integration check.
