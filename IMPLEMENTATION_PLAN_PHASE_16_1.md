# Phase 16.1 — Long-Term Memory Wiring

**Agent:** `python-fastapi`
**Depends on:** None (runs first)
**Fixes:** §5E.2, §5E.4, §5E.5, §9.6, §5C.6 from GAP_ANALYSIS.md
**Source of gaps:** `docs/GAP_ANALYSIS.md` → "Code review findings (2026-04-13)" → CRITICAL #1

## Goal

`PatternRepository`, `FeedbackRepository`, `QCHistoryRepository` currently exist with full CRUD methods but are **never instantiated outside tests**. This phase wires them into the pipeline so:

1. Before the coder runs, it fetches recent approved patterns for the same variable type (cache-like behavior → fewer LLM calls on re-runs).
2. After `human_review`, all approved derivations are written to `PatternRepository` + QC verdicts to `QCHistoryRepository`.
3. Re-running the same spec twice produces different LLM traffic (cache hit visible in logs).

**Out of scope:** `FeedbackRepository` writes happen in Phase 16.2 (tied to new `/reject` and `/approve` payload). This phase only plumbs the session + adds the pattern/QC history paths.

## Architecture change

`PipelineContext` currently holds no DB session — repos would need to open their own. Fix: thread the `AsyncSession` through the context so builtins and tools share it. This matches the existing pattern used for `WorkflowStateRepository` in `src/api/workflow_lifecycle.py`.

## Import-linter exceptions (MUST be added first — task 1.0 below)

This phase deliberately crosses two layer boundaries:
- `src.agents.tools.query_patterns → src.persistence.pattern_repo` — blocked by contract `agents-no-persistence` (`.importlinter` line 107)
- `src.engine.step_builtins → src.persistence.pattern_repo` and `...qc_history_repo` — blocked by contract `engine-no-persistence` (`.importlinter` line 119)

These are **deliberate exceptions** following the existing pattern for `workflow_manager → workflow_state_repo`. The rationale: persistence is accessed at the orchestration boundary using explicit DI via `ctx.session`, not via a hidden module-level singleton. Tool and builtin are thin wrappers that both null-check the session.

The `.importlinter` edits MUST land BEFORE any Python changes, otherwise the pre-push hook blocks every commit.

---

## Files to create

### `src/agents/tools/query_patterns.py` (NEW)
**Purpose:** PydanticAI tool that fetches recent approved patterns matching a variable's rule logic, so the coder agent can use them as reference before generating fresh code.
**Signature:**
```python
@traced_tool("query_patterns")
async def query_patterns(ctx: RunContext[CoderDeps]) -> str: ...
```
**Behavior:**
- Read `ctx.deps.session` — if `None`, return `"No pattern history available."` (graceful when session not wired, e.g. in unit tests).
- Call `PatternRepository(session).query_by_type(variable_type=ctx.deps.rule.variable, limit=3)`.
- Format each `PatternRecord` as: `=== PATTERN {i} (study={study}, approach={approach}) ===\n{approved_code}`.
- Return joined string or `"No prior patterns found for this variable."`.
**Constraints:**
- MUST use the shared session from `ctx.deps.session` — never create a new one.
- Never raise on empty result — return a human-readable "no history" message.
- Keep the tool output under ~2KB to avoid prompt bloat — cap at 3 patterns.
- Use `@traced_tool("query_patterns")` decorator (same as `inspect_data`).
**Reference:** `src/agents/tools/inspect_data.py` — follow the exact docstring + decorator + `RunContext[CoderDeps]` pattern.

### `tests/unit/test_query_patterns_tool.py` (NEW)
**Purpose:** Unit tests for the new tool.
**Tests to write:**
- `test_query_patterns_with_empty_db_returns_no_history_message` — session provided, empty table.
- `test_query_patterns_returns_formatted_patterns_when_found` — seed 2 rows for `AGEGR1`, assert both appear in output.
- `test_query_patterns_respects_variable_type_filter` — seed rows for `AGEGR1` and `TRTDUR`, query for `AGEGR1`, assert only AGEGR1 rows returned.
- `test_query_patterns_with_no_session_returns_unavailable_message` — `CoderDeps(session=None, ...)`, assert returns `"No pattern history available."`.
- `test_query_patterns_caps_at_three_patterns` — seed 10 rows, assert exactly 3 in output.
**Fixtures:** Reuse `async_db_session` fixture from `tests/conftest.py`. Use `PatternRepository.store(...)` directly to seed.
**Pattern:** AAA, `test_<action>_<scenario>_<expected>`.

### `tests/unit/test_save_patterns_builtin.py` (NEW)
**Purpose:** Unit tests for the new `save_patterns` builtin.
**Tests to write:**
- `test_save_patterns_writes_approved_nodes_to_pattern_repo` — ctx with 3 approved DAG nodes, run builtin, assert 3 rows in `patterns` table.
- `test_save_patterns_skips_non_approved_nodes` — mix of approved + failed nodes, only approved get saved.
- `test_save_patterns_writes_qc_verdicts_to_qc_history` — assert 3 rows in `qc_history`.
- `test_save_patterns_with_no_session_is_noop` — ctx with `session=None`, no error, no writes.
- `test_save_patterns_with_empty_dag_is_noop` — empty `ctx.dag.nodes`, no writes.
**Fixtures:** Reuse `async_db_session`; build ctx via a helper that creates a small DAG with 3 nodes.

### `tests/integration/test_long_term_memory.py` (NEW)
**Purpose:** End-to-end test that exercises the full memory loop.
**Tests to write:**
- `test_two_runs_of_same_spec_second_run_finds_patterns` — run `simple_mock.yaml` twice, assert `patterns` table has N rows after run 1 and the same N rows still there after run 2, AND assert `query_patterns` tool returns non-empty when called manually with the same variable name.
**Pattern:** End-to-end via `create_pipeline_orchestrator()` + `interpreter.run()`, mocked LLM.

### `src/agents/tools/__init__.py` (IMPLICITLY NEW RE-EXPORT)
Already exists — see "Files to modify" below.

---

## Files to modify

### `.importlinter` (MOD — task 1.0, must run FIRST)
**Change:** Extend `ignore_imports` on two contracts to allow the new `agents→persistence` and `engine→persistence` edges introduced in this phase.
**Exact change:**

In contract `[importlinter:contract:agents-no-persistence]` (line ~107), add:
```
ignore_imports =
    src.agents.tools.query_patterns -> src.persistence.pattern_repo
```

In contract `[importlinter:contract:engine-no-persistence]` (line ~119), add:
```
ignore_imports =
    src.engine.step_builtins -> src.persistence.pattern_repo
    src.engine.step_builtins -> src.persistence.qc_history_repo
```

Add a comment block above the agents-no-persistence ignore list mirroring the existing style:
```
# ARCHITECTURAL EXCEPTION (not violation):
# query_patterns tool reads validated patterns from long-term memory to seed
# code generation. Accesses session via explicit DI through CoderDeps.session,
# never via module-level singleton. Mirrors the workflow_manager exception
# pattern: persistence is accessed at an orchestration boundary with a lifecycle-
# managed session, not by internal business logic.
```

**Constraints:**
- Must run as task 1.0 (first task). All subsequent Python changes depend on this.
- Run `uv run lint-imports` immediately after to confirm contracts still parse.

### `src/engine/pipeline_context.py` (MOD)
**Change:** Add `session: AsyncSession | None = None` field (defaults to None so tests can build ctxs without DB).
**Exact change:** Add to dataclass fields (after `llm_base_url`):
```python
session: AsyncSession | None = None
```
Add `TYPE_CHECKING` import for `AsyncSession`.
**Constraints:** Default `None` — never assume it's set. Every consumer must null-check.

### `src/factory.py` (MOD)
**Change:** Pass `session` into the `PipelineContext` it constructs.
**Exact change:** In `create_pipeline_orchestrator()`, after `ctx = PipelineContext(...)`, set `ctx.session = session`. Or (cleaner) pass `session=session` in the `PipelineContext(...)` constructor call.
**Constraints:** The session is already created on line 38 — just thread it through.

### `src/agents/deps.py` (MOD)
**Change:** Add `session: AsyncSession | None = None` field to `CoderDeps` dataclass.
**Exact change:**
```python
@dataclass
class CoderDeps:
    df: pd.DataFrame
    synthetic_csv: str
    rule: DerivationRule
    available_columns: list[str]
    session: AsyncSession | None = None
```
Add TYPE_CHECKING import at the top of the file:
```python
if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from src.domain.models import DerivationRule, SpecMetadata
```
(Preserves the existing `DerivationRule, SpecMetadata` TYPE_CHECKING import; just adds `AsyncSession` alongside.)
**Constraints:**
- Default `None`. Existing tests that build `CoderDeps` without session must keep passing (verify with `uv run pytest tests/unit/test_agents.py` before moving on).
- `AsyncSession` is imported from sqlalchemy (external dep), not from `src.persistence`, so no layer violation.

### `src/engine/derivation_runner.py` (MOD)
**Change:** Thread `ctx.session` into `CoderDeps` when building deps in `_run_coder_and_qc`.
**Exact change:** In `_run_coder_and_qc`, change:
```python
deps = CoderDeps(df=df, synthetic_csv=synthetic_csv, rule=rule, available_columns=available)
```
to accept and pass a session. Need to propagate session through `run_variable` parameter (add `session: AsyncSession | None = None`), and update `ParallelMapStepExecutor` in `step_executors.py` to pass `session=ctx.session` when calling `run_variable`.
**Constraints:** Session is optional — `None` means "no pattern history available", not an error.

### `src/engine/step_executors.py` (MOD — `ParallelMapStepExecutor`)
**Change:** Pass `ctx.session` into `run_variable(...)` call.
**Exact change:** Add `session=ctx.session` to the `run_variable(...)` call inside the layer loop.

### `src/engine/step_builtins.py` (MOD — add new builtin)
**Change:** Add `_builtin_save_patterns` + register in `BUILTIN_REGISTRY`.
**Exact change:** New function:
```python
async def _builtin_save_patterns(step: StepDefinition, ctx: PipelineContext) -> None:
    """Persist approved DAG nodes to PatternRepository + QC verdicts to QCHistoryRepository."""
    if ctx.session is None or ctx.dag is None or ctx.spec is None:
        return
    from src.domain.models import DerivationStatus
    from src.persistence.pattern_repo import PatternRepository
    from src.persistence.qc_history_repo import QCHistoryRepository

    pattern_repo = PatternRepository(ctx.session)
    qc_repo = QCHistoryRepository(ctx.session)
    study = ctx.spec.metadata.study

    for variable in ctx.dag.execution_order:
        node = ctx.dag.get_node(variable)
        if node.status != DerivationStatus.APPROVED or node.approved_code is None:
            continue
        await pattern_repo.store(
            variable_type=node.rule.variable,
            spec_logic=node.rule.logic,
            approved_code=node.approved_code,
            study=study,
            approach=node.coder_approach or "",
        )
        if node.qc_verdict is not None:
            await qc_repo.store(
                variable=node.rule.variable,
                verdict=node.qc_verdict,
                coder_approach=node.coder_approach or "",
                qc_approach=node.qc_approach or "",
                study=study,
            )
    await ctx.session.commit()
```
Register in `BUILTIN_REGISTRY`: `"save_patterns": _builtin_save_patterns`.
**Constraints:**
- Null-check `ctx.session`, `ctx.dag`, `ctx.spec`.
- Use `DerivationStatus.APPROVED` enum, not string literal.
- Commit at the end (not inside the loop).
- Import inside function to avoid circular imports at module load time (matches existing pattern in this file).

### `src/agents/tools/__init__.py` (MOD)
**Change:** Re-export `query_patterns`.
**Exact change:** Add `from src.agents.tools.query_patterns import query_patterns` and add `"query_patterns"` to `__all__`.

### `config/agents/coder.yaml` (MOD)
**Change:** Add `query_patterns` to the `tools` list.
**Exact change:** Line 5-7, change:
```yaml
tools:
  - inspect_data
  - execute_code
```
to:
```yaml
tools:
  - inspect_data
  - execute_code
  - query_patterns
```
Update `system_prompt` to instruct the agent: "First check prior patterns via query_patterns. If a good match exists, adapt it rather than generating from scratch."

### `config/agents/qc_programmer.yaml` (MOD)
**Change:** Add `query_patterns` to the `tools` list.
**Exact change:** Same as coder.yaml, but system prompt note should say: "You may call query_patterns to see prior patterns BUT must implement a DIFFERENT approach — never copy."

### `config/pipelines/clinical_derivation.yaml` (MOD)
**Change:** Add a `save_patterns` step after `human_review`, before `audit`.
**Exact change:** Insert between the `human_review` and `audit` blocks:
```yaml
    - id: save_patterns
      type: builtin
      builtin: save_patterns
      depends_on: [human_review]
      description: "Persist approved derivations to long-term memory"
```
Then update `audit.depends_on` from `[human_review]` to `[save_patterns]`.

### `config/pipelines/express.yaml` — **NO CHANGE**
**Rationale:** Express pipeline has no HITL gate and no QC — it's explicitly "rapid prototyping". Patterns should represent **human-validated** approved code, not rubber-stamped express output. Saving patterns from express runs would pollute long-term memory with unverified code. Skip this file entirely.

### `config/pipelines/enterprise.yaml` (MOD)
**Change:** Enterprise has 3 HITL gates (spec_approval, variable_review, final_signoff). Patterns should be saved AFTER `variable_review` (mirrors clinical_derivation's placement after `human_review`), BEFORE `audit`.
**Exact change:** Insert between the `variable_review` and `audit` step blocks:
```yaml
    - id: save_patterns
      type: builtin
      builtin: save_patterns
      depends_on: [variable_review]
      description: "Persist approved derivations to long-term memory"
```
Then update the existing `audit` step's `depends_on` from `[variable_review]` to `[save_patterns]`.
**Constraints:**
- Only ONE `save_patterns` step in the pipeline — do NOT also save after `spec_approval` (spec approval is a different kind of human action) or after `final_signoff` (too late; approved code has already gone through `audit`).
- Same position as clinical_derivation: after the variable-level HITL gate, before `audit`.

---

## Test constraints

- **No LLM calls in unit tests** — the `query_patterns` tool tests don't need an agent. Test the function directly by building a `RunContext[CoderDeps]` stub.
- **Integration test must run end-to-end with mocked LLM** — use the existing mock LLM pattern from `tests/integration/test_workflow.py` or similar.
- Coverage target: new code must have >90% coverage (matches `domain/` target).

## Tooling gate (after Sonnet completes)

```bash
uv run pyright .
uv run ruff check . --fix
uv run ruff format .
uv run pytest tests/unit/test_query_patterns_tool.py tests/unit/test_save_patterns_builtin.py tests/integration/test_long_term_memory.py -v
uv run pytest  # full suite — no regressions
uv run lint-imports
```

## Acceptance criteria

1. ✅ `.importlinter` updated with exception `ignore_imports` entries; `uv run lint-imports` passes.
2. ✅ `query_patterns` tool registered in both coder and qc_programmer agents, returns real patterns when session + data exist.
3. ✅ `save_patterns` builtin runs after HITL gate in clinical_derivation + enterprise pipelines (NOT express — rationale: express has no HITL). Approved nodes appear in `patterns` table, QC verdicts in `qc_history`.
4. ✅ Running `adsl_cdiscpilot01.yaml` twice in a row → second run's `patterns` table has the rows from run 1 (cross-run learning verified).
5. ✅ Running express pipeline → `patterns` table remains empty for that run (no pattern pollution).
6. ✅ All 259 existing tests still pass (zero regressions).
7. ✅ New test files add ≥10 new passing tests.
8. ✅ Full tooling gate is green (pyright, ruff, import-linter, pytest).
