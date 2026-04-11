# Implementation Plan — Phase 14.2: Pipeline Interpreter + FSM Auto-Generation

**Date:** 2026-04-11
**Feature:** F02/F03 — Pipeline interpreter that reads YAML and executes steps + auto-generated FSM
**Agent:** `python-fastapi`
**Dependencies:** Phase 14.1 must be complete — `pipeline_models.py`, `pipeline_context.py`, `step_executors.py` must exist.

---

## Context for Subagent

Phase 14.1 created the pipeline models (YAML schema), step executors (5 types), and the pipeline context. This phase builds the **interpreter** that ties them together: reads a pipeline YAML, generates an FSM from the step graph, and executes steps in topological order.

It also creates the **default pipeline YAML** that reproduces the current hardcoded orchestrator behavior — proving backward compatibility.

**Key files to read first:**
- `src/domain/pipeline_models.py` (from Phase 14.1) — `PipelineDefinition`, `StepDefinition`, `StepType`, `load_pipeline`
- `src/engine/step_executors.py` (from Phase 14.1) — `STEP_EXECUTOR_REGISTRY`, executor classes
- `src/engine/pipeline_context.py` (from Phase 14.1) — `PipelineContext`
- `src/domain/workflow_fsm.py` — current hardcoded FSM (to understand the pattern we're replacing)
- `src/engine/orchestrator.py` — current hardcoded `run()` method (to map each step to YAML)
- `src/domain/exceptions.py` — exception hierarchy

---

## Files to Create

### 1. `src/engine/pipeline_interpreter.py` (NEW)

**Purpose:** The core orchestration engine. Reads a `PipelineDefinition`, builds an execution graph (topological sort of steps based on `depends_on`), generates FSM states, and runs steps sequentially in dependency order.

**Class to define:**

```python
from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from loguru import logger

from src.domain.exceptions import CDDEError
from src.domain.models import AgentName, AuditAction
from src.domain.pipeline_models import PipelineDefinition, StepDefinition

if TYPE_CHECKING:
    from src.engine.pipeline_context import PipelineContext


class PipelineInterpreter:
    """Reads a pipeline definition and executes steps in dependency order.

    The interpreter is a thin loop — all business logic lives in step executors.
    """

    def __init__(self, pipeline: PipelineDefinition, ctx: PipelineContext) -> None:
        self._pipeline = pipeline
        self._ctx = ctx
        self._execution_order = _topological_sort(pipeline.steps)
        self._current_step: str | None = None

    @property
    def current_step(self) -> str | None:
        """The ID of the currently executing step, or None if not started/finished."""
        return self._current_step

    @property
    def pipeline(self) -> PipelineDefinition:
        return self._pipeline

    async def run(self) -> None:
        """Execute all pipeline steps in topological order."""
        logger.info(
            "Starting pipeline '{name}' ({n} steps)",
            name=self._pipeline.name,
            n=len(self._execution_order),
        )
        self._ctx.audit_trail.record(
            variable="",
            action=AuditAction.STEP_STARTED,
            agent=AgentName.ORCHESTRATOR,
            details={"pipeline": self._pipeline.name, "steps": [s.id for s in self._execution_order]},
        )

        for step in self._execution_order:
            self._current_step = step.id
            await self._execute_step(step)

        self._current_step = None
        logger.info("Pipeline '{name}' completed successfully", name=self._pipeline.name)

    async def _execute_step(self, step: StepDefinition) -> None:
        """Execute a single step, dispatching to the correct executor."""
        from src.engine.step_executors import STEP_EXECUTOR_REGISTRY

        executor = STEP_EXECUTOR_REGISTRY.get(step.type)
        if executor is None:
            msg = f"No executor registered for step type '{step.type}'"
            raise CDDEError(msg)

        logger.info("Executing step '{step_id}' (type={type})", step_id=step.id, type=step.type)
        start = time.perf_counter()

        try:
            await executor.execute(step, self._ctx)
        except CDDEError:
            raise  # Domain errors propagate as-is
        except Exception as exc:
            msg = f"Step '{step.id}' failed: {exc}"
            raise CDDEError(msg) from exc

        elapsed = time.perf_counter() - start
        logger.info(
            "Step '{step_id}' completed in {elapsed:.2f}s",
            step_id=step.id,
            elapsed=elapsed,
        )


def _topological_sort(steps: list[StepDefinition]) -> list[StepDefinition]:
    """Sort steps by dependency order. Raises CDDEError if cycle detected.

    Uses Kahn's algorithm (BFS-based topological sort).
    """
    step_map: dict[str, StepDefinition] = {s.id: s for s in steps}
    # Validate all depends_on references exist
    for step in steps:
        for dep in step.depends_on:
            if dep not in step_map:
                msg = f"Step '{step.id}' depends on unknown step '{dep}'"
                raise CDDEError(msg)

    # Build in-degree map
    in_degree: dict[str, int] = {s.id: 0 for s in steps}
    adjacency: dict[str, list[str]] = {s.id: [] for s in steps}
    for step in steps:
        for dep in step.depends_on:
            adjacency[dep].append(step.id)
            in_degree[step.id] += 1

    # BFS from nodes with zero in-degree
    queue = [sid for sid, deg in in_degree.items() if deg == 0]
    result: list[StepDefinition] = []

    while queue:
        # Sort queue for deterministic ordering when multiple steps have zero in-degree
        queue.sort()
        current = queue.pop(0)
        result.append(step_map[current])
        for neighbor in adjacency[current]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(result) != len(steps):
        msg = "Pipeline has circular dependencies"
        raise CDDEError(msg)

    return result
```

**Constraints:**
- `from __future__ import annotations` at top
- Import `STEP_EXECUTOR_REGISTRY` INSIDE `_execute_step` to avoid circular imports
- `_topological_sort` is a module-level function, not a method (testable independently)
- Cycle detection raises `CDDEError` with descriptive message
- Missing dependency reference raises `CDDEError` (not silent skip)
- Every step exception is caught and wrapped in `CDDEError` — except `CDDEError` itself which propagates
- `_current_step` property lets the API know which step is active (for UI status display)
- File MUST be under 120 lines

**Reference:** `src/engine/orchestrator.py` for the logging + audit trail pattern

---

### 2. `config/pipelines/clinical_derivation.yaml` (NEW)

**IMPORTANT:** The `config/pipelines/` directory does not exist yet. Create it before writing the file:
```bash
mkdir -p config/pipelines
```

**Purpose:** Default pipeline config that exactly reproduces the current hardcoded orchestrator flow. This is Scenario 1 — backward compatibility proof.

```yaml
pipeline:
  name: clinical_derivation
  version: "1.0"
  description: "Standard SDTM → ADaM derivation with double-programming QC and human review"

  steps:
    - id: parse_spec
      type: builtin
      builtin: parse_spec
      description: "Parse transformation spec, load source data, generate synthetic CSV"

    - id: build_dag
      type: builtin
      builtin: build_dag
      depends_on: [parse_spec]
      description: "Build derivation dependency graph from spec rules"

    - id: derive_variables
      type: parallel_map
      over: dag_layers
      depends_on: [build_dag]
      description: "Derive each variable with coder+QC double programming, verify, debug if mismatch"

    - id: human_review
      type: hitl_gate
      depends_on: [derive_variables]
      config:
        message: "Review all derivations — inspect DAG, code, and QC results before audit"
      description: "Human-in-the-loop approval gate"

    - id: audit
      type: agent
      agent: auditor
      depends_on: [human_review]
      description: "Generate regulatory audit summary"

    - id: export
      type: builtin
      builtin: export_adam
      depends_on: [audit]
      config:
        formats:
          - csv
          - parquet
      description: "Export derived ADaM dataset"
```

**Constraints:**
- Step IDs are snake_case
- The `depends_on` edges form a linear chain (no branching in the standard flow)
- `derive_variables` uses `parallel_map` over `dag_layers` — this delegates to the existing `run_variable` function per variable per layer
- `parse_spec` is a NEW builtin that encapsulates what `_step_spec_review()` does

---

### 3. `src/engine/step_executors.py` (MODIFY — from Phase 14.1)

**Change:** Add the `parse_spec` builtin to `BUILTIN_REGISTRY`.

**Add this function before the `BUILTIN_REGISTRY` dict:**

```python
async def _builtin_parse_spec(step: StepDefinition, ctx: PipelineContext) -> None:
    """Parse spec, load source data, generate synthetic CSV — mirrors orchestrator._step_spec_review."""
    from src.domain.source_loader import load_source_data
    from src.domain.spec_parser import parse_spec
    from src.domain.synthetic import generate_synthetic

    spec_path = ctx.step_outputs.get("_init", {}).get("spec_path")
    if spec_path is None:
        msg = f"Step '{step.id}' requires '_init.spec_path' in context"
        raise ValueError(msg)
    ctx.spec = parse_spec(spec_path)
    source_df = load_source_data(ctx.spec)
    ctx.derived_df = source_df.copy()
    ctx.synthetic_csv = generate_synthetic(source_df, rows=ctx.spec.synthetic.rows).to_csv(index=False)
```

**Add to BUILTIN_REGISTRY:**
```python
BUILTIN_REGISTRY: dict[str, Any] = {
    "parse_spec": _builtin_parse_spec,
    "build_dag": _builtin_build_dag,
    "export_adam": _builtin_export_adam,
}
```

**Also: the caller (factory or API) must seed `ctx.step_outputs["_init"]["spec_path"]` before calling `interpreter.run()`.** This is documented in the PipelineContext docstring.

---

### 4. `tests/unit/test_pipeline_interpreter.py` (NEW)

**Purpose:** Tests for topological sort, cycle detection, and interpreter step dispatching.

**Tests to write:**

```python
def test_topological_sort_linear_chain_preserves_order() -> None:
    """Steps with linear depends_on are sorted in dependency order."""
    # Arrange
    steps = [
        StepDefinition(id="c", type=StepType.BUILTIN, builtin="x", depends_on=["b"]),
        StepDefinition(id="a", type=StepType.BUILTIN, builtin="x"),
        StepDefinition(id="b", type=StepType.BUILTIN, builtin="x", depends_on=["a"]),
    ]
    # Act
    result = _topological_sort(steps)
    # Assert
    ids = [s.id for s in result]
    assert ids == ["a", "b", "c"]


def test_topological_sort_parallel_steps_sorted_alphabetically() -> None:
    """Steps with no dependencies between them are sorted alphabetically (deterministic)."""
    steps = [
        StepDefinition(id="z", type=StepType.BUILTIN, builtin="x"),
        StepDefinition(id="a", type=StepType.BUILTIN, builtin="x"),
        StepDefinition(id="m", type=StepType.BUILTIN, builtin="x"),
    ]
    result = _topological_sort(steps)
    ids = [s.id for s in result]
    assert ids == ["a", "m", "z"]


def test_topological_sort_cycle_raises_cdde_error() -> None:
    """Circular dependencies raise CDDEError."""
    steps = [
        StepDefinition(id="a", type=StepType.BUILTIN, builtin="x", depends_on=["b"]),
        StepDefinition(id="b", type=StepType.BUILTIN, builtin="x", depends_on=["a"]),
    ]
    with pytest.raises(CDDEError, match="circular dependencies"):
        _topological_sort(steps)


def test_topological_sort_unknown_dependency_raises_cdde_error() -> None:
    """Reference to non-existent step raises CDDEError."""
    steps = [
        StepDefinition(id="a", type=StepType.BUILTIN, builtin="x", depends_on=["nonexistent"]),
    ]
    with pytest.raises(CDDEError, match="unknown step 'nonexistent'"):
        _topological_sort(steps)


def test_load_default_pipeline_parses_without_error() -> None:
    """The default clinical_derivation.yaml pipeline parses successfully."""
    pipeline = load_pipeline("config/pipelines/clinical_derivation.yaml")
    assert pipeline.name == "clinical_derivation"
    assert len(pipeline.steps) == 6
    step_ids = [s.id for s in pipeline.steps]
    assert "parse_spec" in step_ids
    assert "human_review" in step_ids
    assert "export" in step_ids
```

**Constraints:**
- Import `_topological_sort` from `src.engine.pipeline_interpreter`
- Import `load_pipeline` from `src.domain.pipeline_models`
- Import `CDDEError` from `src.domain.exceptions`
- All tests are sync (topological sort is not async) — except if testing interpreter.run()
- The `test_load_default_pipeline` test validates the YAML file we ship
- AAA comments, `test_<action>_<scenario>_<expected>` naming

**Reference:** `tests/unit/test_spec_parser.py` for YAML parsing + error tests

---

### 5. `docs/COMPOSITION_LAYER.md` (NEW)

**Purpose:** Architecture justification document explaining why CDDE builds a YAML composition layer on top of PydanticAI, and how it compares to alternatives.

**Content outline:**

```markdown
# Composition Layer — Why YAML-Driven Orchestration

## The Gap PydanticAI Leaves Open

PydanticAI provides excellent agent abstractions:
- Typed dependency injection via `RunContext[DepsType]`
- Structured output validation via Pydantic models
- Tool binding with automatic schema generation
- Multi-turn conversation with tool use
- Retry with exponential backoff

What PydanticAI does NOT provide:
- **Multi-agent orchestration** — no built-in way to sequence, parallelize, or conditionally route between agents
- **Workflow state management** — no FSM, no persistent state between agent calls
- **Human-in-the-loop gates** — no approval mechanism
- **Pipeline configuration** — composition is always Python code

This is by design. PydanticAI's documentation explicitly states it's an agent framework, not a workflow engine. The composition layer is the developer's responsibility.

## Why Not Use an Existing Orchestrator?

| Framework | Why Not |
|-----------|---------|
| **CrewAI** | `async_execution` has known bugs (PR #2466). `human_input` is CLI-only. Hierarchical process is unpredictable. Stringly-typed. |
| **LangGraph** | Heavy LangChain dependency. Graph-first, not agent-first. Would require rewriting all agents. |
| **Prefect / Airflow** | Designed for data pipelines, not LLM agent orchestration. No native HITL or agent abstractions. |
| **Temporal** | Production-grade but massive infrastructure overhead for a homework project. |

## Our Approach: Thin YAML Composition Layer

Instead of adopting a framework, we built a ~300-line interpreter that:
1. **Reads pipeline YAML** — steps, dependencies, composition types
2. **Topologically sorts steps** — respects `depends_on` edges
3. **Dispatches to typed executors** — each `StepType` has a dedicated executor class
4. **Generates FSM states from pipeline** — no manual FSM maintenance
5. **Passes context between steps** — typed `PipelineContext` dataclass

### Composition Primitives

| Type | PydanticAI Equivalent | Our Layer |
|------|----------------------|-----------|
| Single agent call | `agent.run()` | `AgentStepExecutor` |
| Parallel agents | `asyncio.gather(a.run(), b.run())` | `GatherStepExecutor` |
| Map over collection | Manual `for` loop | `ParallelMapStepExecutor` |
| Non-LLM function | Plain Python | `BuiltinStepExecutor` |
| Human approval | Not supported | `HITLGateStepExecutor` |

### Trade-offs

**What we gain:**
- Clinical teams can customize pipelines without Python changes
- New studies can skip QC (rapid prototyping) or add extra gates (enterprise compliance)
- Pipeline diagram auto-generated from YAML for regulatory presentations
- FSM states auto-generated — no drift between pipeline and state machine

**What we accept:**
- Step executors still contain Python logic (agent deps building, DAG construction)
- Not a general-purpose workflow engine — pharma-specific composition types
- No dynamic branching mid-execution (pipeline is fixed at start)

## Comparison to CrewAI YAML

CrewAI also supports YAML configuration, but at a different level:

| Concern | CrewAI YAML | CDDE Pipeline YAML |
|---------|-------------|-------------------|
| Agent definition | ✅ role, goal, backstory | ✅ name, system_prompt, tools, retries |
| Task definition | ✅ description, agent, tools | ✅ step id, type, agent, config |
| Orchestration | ❌ Hardcoded Process class | ✅ Configurable step graph with depends_on |
| Parallelism | ❌ Buggy async_execution flag | ✅ `gather` and `parallel_map` primitives |
| HITL gates | ❌ CLI stdin only | ✅ `hitl_gate` step with web UI integration |
| FSM | ❌ None | ✅ Auto-generated from pipeline steps |
```

**Constraints:**
- This is a documentation file — no code
- Keep it under 120 lines
- Reference specific CDDE files and classes (not abstract descriptions)
- Include the comparison table with CrewAI — this is important for the Sanofi panel presentation

---

## After Implementation

1. Run: `uv run ruff check . --fix && uv run ruff format .`
2. Run: `uv run pyright .`
3. Run: `uv run lint-imports`
4. Run: `uv run pytest tests/unit/test_pipeline_interpreter.py -v`
5. Run: `uv run pytest` — full suite
6. Verify `config/pipelines/clinical_derivation.yaml` parses: `uv run python -c "from src.domain.pipeline_models import load_pipeline; p = load_pipeline('config/pipelines/clinical_derivation.yaml'); print(f'{p.name}: {len(p.steps)} steps')"`
