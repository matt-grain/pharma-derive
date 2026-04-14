# Phase 17.1 — LTM Read Loop Expansion (Bug #5)

**Bug:** BUGS.md #5 — `query_patterns` is the only LTM tool wired into the coder agent. The `feedback` and `qc_history` tables are write-only — humans correct the agent, the agent never sees the corrections.

**Goal:** Add two new coder tools (`query_feedback` + `query_qc_history`) so the LLM sees three distinct LTM signal sources and can weigh them by authority (human > debugger > prior agent).

**Agent:** `python-fastapi`
**Depends on:** Nothing (independent of 17.2 and 17.3)
**Estimated effort:** 1.5–2 hours
**Reference (read first):** BUGS.md §#5 (full proposal), `src/agents/tools/query_patterns.py` (canonical pattern for new tools), `tests/unit/test_query_patterns_tool.py` (canonical test pattern), `config/agents/coder.yaml` (current tool list and system prompt)

---

## Files to create — 7 new

### `src/agents/tools/query_feedback.py` (NEW)
**Purpose:** PydanticAI tool that returns recent human reviewer feedback (approve/reject/override) for the current variable type, formatted for the coder agent's prompt context.
**Pattern:** Follow `src/agents/tools/query_patterns.py` exactly — same import shape (`RunContext` at runtime + `noqa: TC002`), same `@traced_tool("query_feedback")` decorator from `src.agents.tools.tracing`, same shape of `_format_X(...)` helper, same fall-through (no repo → "No feedback history available.", empty rows → "No prior feedback found for this variable.").
**Public function:** `async def query_feedback(ctx: RunContext[CoderDeps]) -> str`
**Logic:**
1. Read `repo = ctx.deps.feedback_repo` (NEW field on CoderDeps — see Modified Files section)
2. If `repo is None`: return `"No feedback history available."`
3. `variable = ctx.deps.rule.variable`
4. `records = await repo.query_by_variable(variable=variable, limit=3)` (existing method on FeedbackRepository — already returns `list[FeedbackRecord]`)
5. If `records` is empty: return `"No prior feedback found for this variable."`
6. Format each row as:
   ```
   === FEEDBACK 1 (variable={variable}, action={action_taken}, study={study}) ===
   Reason: {feedback}
   {action_phrase}
   ```
   where `action_phrase` is one of three hard-coded strings depending on `action_taken`:
   - `'approved'` → `"The human reviewer approved this approach. Repeating it is safe."`
   - `'rejected'` → `"The human reviewer rejected the previous coder's approach. Avoid generating similar code."`
   - `'overridden'` → `"The human reviewer replaced the coder's code with a different implementation. Consider this preference when generating new code."`
7. Join the formatted records with `"\n\n"` and return the string
**Constraints:**
- No mutable default arguments
- No bare `except:` — let exceptions propagate (the @traced_tool decorator handles tracing)
- Tool function must be `async`
- Use `from __future__ import annotations` at the top
- The 3 action_phrase strings should live as a module-level `Final[dict[str, str]]` constant for easy editing
**Reference:** `src/agents/tools/query_patterns.py` — copy the structure exactly, swap the repo + format helper

---

### `src/agents/tools/query_qc_history.py` (NEW)
**Purpose:** PydanticAI tool that returns recent QC verdict history (coder/QC matches and mismatches) for the current variable type, so the coder can avoid known edge cases.
**Pattern:** Same as `query_feedback.py` (which is itself modeled on `query_patterns.py`).
**Public function:** `async def query_qc_history(ctx: RunContext[CoderDeps]) -> str`
**Logic:**
1. Read `repo = ctx.deps.qc_history_repo` (NEW field on CoderDeps)
2. If `repo is None`: return `"No QC history available."`
3. `variable = ctx.deps.rule.variable`
4. `records = await repo.query_by_variable(variable=variable, limit=3)` (NEW method on QCHistoryRepository — see Modified Files section)
5. If `records` is empty: return `"No prior QC history for this variable."`
6. Format each row as:
   ```
   === QC HISTORY 1 (variable={variable}, study={study}, verdict={verdict}) ===
   Coder approach: {coder_approach}
   QC approach: {qc_approach}
   {verdict_phrase}
   ```
   where `verdict_phrase` is hard-coded by verdict value:
   - `'match'` → `"Coder and QC agreed on this implementation — safe pattern to repeat."`
   - `'mismatch'` → `"Coder and QC disagreed. The debugger resolved this mismatch in a previous run. Watch for the same edge case."`
7. Join with `"\n\n"` and return
**Constraints:** Same as `query_feedback.py`. The `verdict_phrase` constants in a module-level `Final[dict[str, str]]`.
**Reference:** `src/agents/tools/query_patterns.py`

---

### `tests/unit/test_query_feedback_tool.py` (NEW)
**Purpose:** Unit tests for `query_feedback` tool.
**Pattern:** Mirror `tests/unit/test_query_patterns_tool.py` exactly — same fixture shape, same MagicMock approach for RunContext, same per-scenario tests.
**Tests to write (5 minimum, mirroring test_query_patterns_tool.py 1:1):**
- `test_query_feedback_with_no_repo_returns_unavailable_message` — pass `feedback_repo=None`, expect `"No feedback history available."`
- `test_query_feedback_with_empty_db_returns_no_history_message` — empty in-memory SQLite, expect `"No prior feedback found for this variable."`
- `test_query_feedback_returns_formatted_rows_when_found` — seed 3 rows (1 approved, 1 rejected, 1 overridden), assert `"FEEDBACK 1"`, `"FEEDBACK 2"`, `"FEEDBACK 3"`, all 3 action_phrase strings present, all 3 reasons present
- `test_query_feedback_respects_variable_filter` — seed AGE_GROUP and TREATMENT_DURATION rows, query for AGE_GROUP, assert only AGE_GROUP-related strings appear
- `test_query_feedback_caps_at_three_rows` — seed 10 rows for one variable, assert only `"FEEDBACK 1"`, `"FEEDBACK 2"`, `"FEEDBACK 3"` appear (no `"FEEDBACK 4"`)
**Fixtures:** Use `pattern_repo` fixture pattern from `test_query_patterns_tool.py` but for `FeedbackRepository`. Use AAA markers in every test body (`# Arrange`, `# Act`, `# Assert`).
**Constraints:** No `pytest.raises(Exception)` — always use specific exception types if any. Test names follow `test_<action>_<scenario>_<expected>`. Use `asyncio_mode = "auto"` (no `@pytest.mark.asyncio`).
**Reference:** `tests/unit/test_query_patterns_tool.py` — copy structure, swap repo + tool

---

### `tests/unit/test_query_qc_history_tool.py` (NEW)
**Purpose:** Unit tests for `query_qc_history` tool.
**Pattern:** Same as `test_query_feedback_tool.py` (which mirrors `test_query_patterns_tool.py`).
**Tests to write (5 minimum):**
- `test_query_qc_history_with_no_repo_returns_unavailable_message`
- `test_query_qc_history_with_empty_db_returns_no_history_message`
- `test_query_qc_history_returns_formatted_rows_when_found` — seed 1 match + 1 mismatch row, assert both verdict_phrase strings appear plus the coder_approach and qc_approach strings
- `test_query_qc_history_respects_variable_filter` — seed AGE_GROUP + TREATMENT_DURATION, assert only AGE_GROUP returned
- `test_query_qc_history_caps_at_three_rows`
**Constraints:** Same as test_query_feedback_tool.py.
**Reference:** `tests/unit/test_query_patterns_tool.py`

---

### `tests/integration/test_ltm_three_tools_end_to_end.py` (NEW)
**Purpose:** Integration test that proves the FULL LTM read loop (all 3 tools) can be invoked after a 2-run scenario where Run 1 produces patterns + feedback + qc_history rows, and Run 2's coder reads them.
**Pattern:** Mirror `tests/integration/test_long_term_memory.py::test_two_runs_of_same_spec_second_run_finds_patterns` but extended to seed all 3 tables and call all 3 tools.
**Test to write:**
- `test_three_tools_return_data_after_seeded_run` — single test that:
  1. Initialises an in-memory SQLite (`tmp_path / 'ltm_three_tools.db'`)
  2. Directly seeds `patterns` (via PatternRepository.store), `feedback` (via FeedbackRepository.store), `qc_history` (via QCHistoryRepository.store) for variable `"AGE_GROUP"` — at least 1 row each
  3. Builds 3 mock `RunContext[CoderDeps]` objects (one per tool call) with `MagicMock(spec=RunContext)` and a `CoderDeps` containing all 3 repos pointed at the same session
  4. Calls `await query_patterns(ctx)`, `await query_feedback(ctx)`, `await query_qc_history(ctx)` in sequence
  5. Asserts each returns a non-empty string containing the seeded data (assert `"PATTERN"` in result for query_patterns, `"FEEDBACK"` in result for query_feedback, `"QC HISTORY"` in result for query_qc_history)
**Constraints:** No real LLM calls. Use the same `init_db` + `tmp_path` pattern as the existing integration test. Single test function — keep it focused.
**Reference:** `tests/integration/test_long_term_memory.py`

---

## Files to modify — 6 modified

### `src/agents/deps.py` (MODIFY)
**Change:** Add 2 new fields to `CoderDeps` dataclass: `feedback_repo` and `qc_history_repo`, both `None` by default and both typed under `TYPE_CHECKING`.
**Exact change:**
1. In the `if TYPE_CHECKING:` block (currently has `from src.persistence.pattern_repo import PatternRepository`), add:
   ```python
   from src.persistence.feedback_repo import FeedbackRepository
   from src.persistence.qc_history_repo import QCHistoryRepository
   ```
2. In `class CoderDeps`, after the existing `pattern_repo: PatternRepository | None = None` line, add:
   ```python
   feedback_repo: FeedbackRepository | None = None
   qc_history_repo: QCHistoryRepository | None = None
   ```
**Constraints:** Both fields MUST be typed under `TYPE_CHECKING` only (mirrors the existing `pattern_repo` pattern — engine layer must not import sqlalchemy at runtime). Both default to `None` for backwards compat with existing test fixtures that don't set them.

---

### `src/persistence/qc_history_repo.py` (MODIFY)
**Change:** Add a new `query_by_variable` method that returns recent rows for a given variable, modeled on `FeedbackRepository.query_by_variable`.
**Exact change:** Add the following method to `QCHistoryRepository` (after `get_stats`):
```python
async def query_by_variable(self, variable: str, limit: int = 5) -> list[QCHistoryRecord]:
    """Retrieve recent QC verdict rows for a variable, ordered most-recent first."""
    stmt = (
        select(QCHistoryRow)
        .where(QCHistoryRow.variable == variable)
        .order_by(QCHistoryRow.created_at.desc())
        .limit(limit)
    )
    result = await self._execute(stmt)
    return [
        QCHistoryRecord(
            id=row.id,
            variable=row.variable,
            verdict=row.verdict,
            coder_approach=row.coder_approach,
            qc_approach=row.qc_approach,
            study=row.study,
            created_at=row.created_at.isoformat(),
        )
        for row in result.scalars()
    ]
```
**Prerequisite — verify `QCHistoryRecord` exists in `src/domain/models.py`.** If it doesn't, ADD it as a frozen Pydantic model alongside `PatternRecord` and `FeedbackRecord`, with fields `id: int`, `variable: str`, `verdict: str`, `coder_approach: str`, `qc_approach: str`, `study: str`, `created_at: str`. Also export from `src/domain/models.py`.
**Constraints:** Returns Pydantic schemas, never ORM rows. Same query pattern as `FeedbackRepository.query_by_variable` (which already exists). Use `select()`, `_execute()`, and the `BaseRepository` helpers — no raw SQL.

---

### `src/factory.py` (MODIFY)
**Change:** Wire `FeedbackRepository` and `QCHistoryRepository` into the orchestrator construction so they get injected into `CoderDeps` alongside the existing `PatternRepository`.
**Exact change:**
1. Find the function `create_pipeline_orchestrator` (or similar — it's the function that builds `PipelineContext` and instantiates the orchestrator)
2. After the line that creates `PatternRepository(session)`, add:
   ```python
   feedback_repo = FeedbackRepository(session)
   qc_history_repo = QCHistoryRepository(session)
   ```
3. Find where `PatternRepository` is assigned to `ctx.pattern_repo` (or `CoderDeps.pattern_repo` — whichever site exists) and add the two new repos to the same site:
   ```python
   ctx.feedback_repo = feedback_repo
   ctx.qc_history_repo = qc_history_repo
   ```
4. Add the imports at the top of factory.py:
   ```python
   from src.persistence.feedback_repo import FeedbackRepository
   from src.persistence.qc_history_repo import QCHistoryRepository
   ```
**Constraints:** Construction MUST happen in `factory.py` (outside `src/engine/` and `src/agents/` per the `check_repo_direct_instantiation` pre-push hook). DO NOT import these repos from inside `src/engine/` or `src/agents/`. Pass the repo instances down via DI, never as singletons.
**Verification:** Run `uv run lint-imports` after the change. The `check_repo_direct_instantiation` hook must still pass.

---

### `src/engine/pipeline_context.py` (MODIFY)
**Change:** Add `feedback_repo` and `qc_history_repo` as optional fields on `PipelineContext`, mirroring the existing `pattern_repo` field.
**Exact change:**
1. Find the existing `pattern_repo: PatternRepository | None = None` field declaration on `PipelineContext`
2. After it, add:
   ```python
   feedback_repo: FeedbackRepository | None = None
   qc_history_repo: QCHistoryRepository | None = None
   ```
3. Add the `TYPE_CHECKING` imports at the top of the file:
   ```python
   from src.persistence.feedback_repo import FeedbackRepository
   from src.persistence.qc_history_repo import QCHistoryRepository
   ```
**Constraints:** Both fields MUST be typed under `TYPE_CHECKING` only (the `check_raw_sql_in_engine` hook bans sqlalchemy imports in `src/engine/` even under `TYPE_CHECKING` — verify by re-reading how `pattern_repo` is currently declared and copy that pattern exactly). If `pattern_repo` is using a string-quoted forward reference instead of a TYPE_CHECKING import, do the same for the two new fields.

---

### `src/engine/derivation_runner.py` (MODIFY)
**Change:** Update `run_variable` (or wherever `CoderDeps` is constructed inside the runner) to pass `feedback_repo` and `qc_history_repo` from the context into `CoderDeps` alongside the existing `pattern_repo`.
**Exact change:**
1. Find the call site that constructs `CoderDeps(...)` inside `run_variable` (search for `CoderDeps(`)
2. The current call already passes `pattern_repo=...` as a kwarg. Add two more kwargs to the SAME call:
   ```python
   feedback_repo=feedback_repo,
   qc_history_repo=qc_history_repo,
   ```
3. Update the function signature of `run_variable` to accept the two new repo parameters (default to `None` for backwards compat with any test that calls it directly):
   ```python
   feedback_repo: FeedbackRepository | None = None,
   qc_history_repo: QCHistoryRepository | None = None,
   ```
4. Add the TYPE_CHECKING imports at the top
5. Update the ParallelMapStepExecutor in `src/engine/step_executors.py` to pass `ctx.feedback_repo` and `ctx.qc_history_repo` into `run_variable` (the existing call site already passes `pattern_repo=ctx.pattern_repo` — add the two new kwargs there too)
**Constraints:** Same TYPE_CHECKING discipline as deps.py and pipeline_context.py. The function signature change is non-breaking because the new params default to `None`.

---

### `src/agents/registry.py` (MODIFY)
**Change:** Register the 2 new tool functions in `TOOL_REGISTRY` so the agent factory can resolve them when loading `coder.yaml`.
**Exact change:**
1. Find the `TOOL_REGISTRY` dict (it currently maps tool name strings to tool functions, e.g. `"query_patterns": query_patterns`)
2. Add two new entries:
   ```python
   "query_feedback": query_feedback,
   "query_qc_history": query_qc_history,
   ```
3. Add the imports at the top:
   ```python
   from src.agents.tools.query_feedback import query_feedback
   from src.agents.tools.query_qc_history import query_qc_history
   ```
**Constraints:** Tool names in the registry must match the `tools:` list entries in YAML configs exactly (case-sensitive). The factory raises a runtime KeyError if a YAML lists a tool not in the registry.

---

### `config/agents/coder.yaml` (MODIFY)
**Change:** Add `query_feedback` and `query_qc_history` to the coder's `tools:` list and update the system prompt to teach the model the priority order.
**Exact change:**
1. In the `tools:` list, after `query_patterns`, add:
   ```yaml
     - query_feedback
     - query_qc_history
   ```
2. Replace the current `system_prompt:` block with:
   ```yaml
   system_prompt: |
     You are a senior statistical programmer. Generate clean, vectorized
     pandas code to derive the requested variable. Your code will be
     executed as: `result = eval(your_code, {'df': df, 'pd': pd, 'np': np})`.
     The result must be a pandas Series with the same index as df.
     Handle null values explicitly.

     Before writing code, query ALL THREE long-term memory sources in this
     order — they come from DIFFERENT sources and weigh differently:

     1. query_feedback — Has a human reviewer rejected or overridden this
        variable before? Their feedback is the STRONGEST signal — adapt your
        code to their preference. A previous rejection means do not propose
        that approach again. An override means use the override's strategy.
     2. query_qc_history — Have prior coder/QC versions disagreed on this
        variable? Where did they disagree, and what did the debugger pick?
        Avoid the same edge case.
     3. query_patterns — What approved code exists for this variable? Use
        it as a starting point only after you have checked feedback and
        QC history.

     Weigh signals by authority: human > debugger > prior agent.
     Then use inspect_data to understand the data schema before writing the
     derivation.
   ```
**Constraints:** Preserve YAML indentation exactly. The `|` block scalar must be followed by indented text (2 spaces) on every line. The 3 numbered tool descriptions must keep the order specified above (priority encoded in order). Don't change `name`, `output_type`, `deps_type`, or `retries` fields.

---

## Implementation order (within Phase 17.1)

1. Domain model — verify/add `QCHistoryRecord` in `src/domain/models.py`
2. Repository — add `QCHistoryRepository.query_by_variable` method
3. Deps — extend `CoderDeps` with the 2 new fields
4. Context — extend `PipelineContext` with the 2 new fields
5. Factory — wire the 2 new repos in `src/factory.py`
6. Runner — pass the 2 new repos through `run_variable` in `derivation_runner.py`
7. Step executor — update ParallelMapStepExecutor's `run_variable` call site to pass the 2 new repos
8. Tools — implement `src/agents/tools/query_feedback.py` and `src/agents/tools/query_qc_history.py`
9. Registry — register the 2 new tools in `src/agents/registry.py`
10. Config — update `config/agents/coder.yaml` (tools list + system prompt)
11. Tests — write the 2 new unit test files + the 1 new integration test file

---

## Tooling gate (mandatory after Phase 17.1)

```bash
cd C:\Projects\Interviews\jobs\Sanofi-AI-ML-Lead\homework
uv run pyright .
uv run ruff check . --fix
uv run ruff format .
uv run lint-imports
uv run pytest tests/ -q
```

All 18 pre-push hooks must remain green. Special attention to:
- `check_repo_direct_instantiation` — must not have new violations in engine/ or agents/
- `check_raw_sql_in_engine` — must not have new sqlalchemy imports in engine/
- `pyright` strict mode — no new `Any` without `# Any: <reason>` comments

---

## Acceptance criteria for Phase 17.1

- ✅ `query_feedback` and `query_qc_history` tools exist as files in `src/agents/tools/` and follow the `query_patterns.py` pattern
- ✅ Both tools are registered in `src/agents/registry.py::TOOL_REGISTRY`
- ✅ `config/agents/coder.yaml` lists both tools and the system prompt teaches priority order
- ✅ `CoderDeps`, `PipelineContext`, and `factory.py` are wired to inject `feedback_repo` and `qc_history_repo`
- ✅ `QCHistoryRepository.query_by_variable` exists and is unit-tested
- ✅ 5+ unit tests for `query_feedback` (mirror test_query_patterns_tool.py 1:1)
- ✅ 5+ unit tests for `query_qc_history` (same pattern)
- ✅ 1+ integration test that calls all 3 LTM tools after seeding all 3 tables
- ✅ All 18 pre-push hooks green
- ✅ Total backend test count ≥ 311 + 11 new = 322

**This phase closes Bug #5.**
