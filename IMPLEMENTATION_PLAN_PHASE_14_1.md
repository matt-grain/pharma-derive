# Implementation Plan — Phase 14.1: Pipeline Models + Step Executors

**Date:** 2026-04-11
**Feature:** F02/F03 — YAML-Driven Orchestration Pipeline (core engine)
**Agent:** `python-fastapi`
**Dependencies:** None (new modules, no modifications to existing orchestrator yet)

---

## Context for Subagent

This project is a Clinical Data Derivation Engine (CDDE). The current orchestrator (`src/engine/orchestrator.py`) has a hardcoded sequence of steps in its `run()` method. We are building a **YAML-driven pipeline system** that lets users define orchestration steps, agent assignments, and composition types in a config file instead of Python code.

**This phase creates the foundation: domain models for pipelines + step executor classes. No existing files are modified — this is purely additive.**

**Key files to read first:**
- `src/domain/models.py` — existing domain models (StrEnum pattern, frozen BaseModel pattern)
- `src/domain/exceptions.py` — existing exception hierarchy (CDDEError base)
- `src/agents/factory.py` — how agents are loaded from YAML
- `src/agents/registry.py` — agent/tool/type registries
- `src/engine/derivation_runner.py` — how `run_variable()` works (coder+QC parallel, verify, debug)
- `src/engine/orchestrator.py` — the current hardcoded step methods to understand what each step does

---

## Files to Create

### 1. `src/domain/pipeline_models.py` (NEW)

**Purpose:** Pydantic models for parsing pipeline YAML configuration files. These are pure domain models — no engine logic, no imports from engine/.

**Classes to define:**

```python
from __future__ import annotations

from enum import StrEnum
from pydantic import BaseModel


class StepType(StrEnum):
    """Composition type for a pipeline step."""
    AGENT = "agent"
    BUILTIN = "builtin"
    GATHER = "gather"
    PARALLEL_MAP = "parallel_map"
    HITL_GATE = "hitl_gate"


class StepDefinition(BaseModel, frozen=True):
    """A single step in a pipeline configuration."""
    id: str
    type: StepType
    description: str = ""
    agent: str | None = None           # agent YAML name, for type=agent
    agents: list[str] | None = None    # multiple agents, for type=gather
    builtin: str | None = None         # builtin function name, for type=builtin
    depends_on: list[str] = []
    config: dict[str, str | int | float | bool | list[str]] = {}
    sub_steps: list[StepDefinition] | None = None  # for type=parallel_map
    condition: str | None = None       # e.g. "verdict == 'mismatch'"
    over: str | None = None            # iteration target for parallel_map, e.g. "dag_layers"


class PipelineDefinition(BaseModel, frozen=True):
    """Top-level pipeline configuration parsed from YAML."""
    name: str
    version: str = "1.0"
    description: str = ""
    steps: list[StepDefinition]


def load_pipeline(yaml_path: str | Path) -> PipelineDefinition:
    """Parse a pipeline YAML file into a PipelineDefinition."""
    from pathlib import Path

    import yaml

    path = Path(yaml_path)
    if not path.exists():
        msg = f"Pipeline config not found: {path}"
        raise FileNotFoundError(msg)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    pipeline_data = raw.get("pipeline", raw)  # support both root-level and nested
    return PipelineDefinition.model_validate(pipeline_data)
```

**Constraints:**
- `from __future__ import annotations` at top
- All models use `frozen=True`
- `StepType` is a `StrEnum` (matching project pattern in `src/domain/models.py`)
- `StepDefinition` is self-referential (`sub_steps: list[StepDefinition] | None`) — Pydantic v2 handles this with `model_rebuild()`. Call `StepDefinition.model_rebuild()` after class definition.
- `load_pipeline` uses `yaml.safe_load` (matching pattern in `src/agents/factory.py`)
- `config` dict values are `str | int | float | bool | list[str]` — NOT `Any`
- File MUST be under 80 lines
- Import `Path` inside `load_pipeline` to keep top-level imports framework-free (domain layer purity)

**Reference:** `src/domain/models.py` for StrEnum + frozen BaseModel pattern

---

### 2. `src/engine/pipeline_context.py` (NEW)

**Purpose:** Mutable state container passed between pipeline steps. Each step reads inputs from the context and writes outputs back. This replaces the current `WorkflowState` for pipeline-driven execution.

**Classes to define:**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any  # Any: heterogeneous step outputs stored by key

if TYPE_CHECKING:
    from pathlib import Path

    import pandas as pd

    from src.audit.trail import AuditTrail
    from src.domain.dag import DerivationDAG
    from src.domain.models import TransformationSpec


@dataclass
class PipelineContext:
    """Shared mutable state passed through pipeline step execution.

    Each step reads its inputs from named keys and writes its outputs back.
    The context also carries cross-cutting concerns (audit trail, workflow ID).
    """

    workflow_id: str
    audit_trail: AuditTrail
    llm_base_url: str
    output_dir: Path | None = None

    # Step outputs — populated during execution
    spec: TransformationSpec | None = None
    source_df: pd.DataFrame | None = None
    derived_df: pd.DataFrame | None = None
    synthetic_csv: str = ""
    dag: DerivationDAG | None = None

    # Pipeline metadata
    step_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Any: step outputs are heterogeneous (DataFrames, specs, audit summaries, etc.)

    errors: list[str] = field(default_factory=list)

    def set_output(self, step_id: str, key: str, value: object) -> None:
        """Store a named output from a step."""
        if step_id not in self.step_outputs:
            self.step_outputs[step_id] = {}
        self.step_outputs[step_id][key] = value

    def get_output(self, step_id: str, key: str) -> object:
        """Retrieve a named output from a previous step."""
        outputs = self.step_outputs.get(step_id)
        if outputs is None:
            msg = f"No outputs found for step '{step_id}'"
            raise KeyError(msg)
        if key not in outputs:
            msg = f"Output '{key}' not found in step '{step_id}'. Available: {list(outputs.keys())}"
            raise KeyError(msg)
        return outputs[key]
```

**Constraints:**
- `from __future__ import annotations` at top
- This is a `@dataclass`, NOT a Pydantic model (matches `WorkflowState` pattern)
- Heavy imports (`pandas`, `DerivationDAG`, etc.) go in `TYPE_CHECKING` block — they're only used as type annotations, and `from __future__ import annotations` makes them strings
- `step_outputs` uses `dict[str, dict[str, Any]]` with a justification comment for `Any`
- `set_output` and `get_output` are the only public methods — no complex logic
- `get_output` raises `KeyError` with descriptive messages (not silent `None` fallback)
- File MUST be under 70 lines

**Reference:** `src/domain/workflow_models.py` for the `WorkflowState` dataclass pattern

---

### 3. `src/engine/step_executors.py` (NEW)

**Purpose:** Base class and 5 concrete step executors. Each executor handles one `StepType` and knows how to run that kind of step.

**IMPORTANT: This file will be ~180 lines. Every executor must handle errors explicitly — Sonnet must NOT leave empty except blocks or skip error paths.**

**Classes to define:**

```python
from __future__ import annotations

import abc
import asyncio
from typing import TYPE_CHECKING

from loguru import logger

from src.domain.models import AgentName, AuditAction
from src.domain.pipeline_models import StepDefinition, StepType

if TYPE_CHECKING:
    from src.engine.pipeline_context import PipelineContext


class StepExecutor(abc.ABC):
    """Base class for pipeline step executors."""

    @abc.abstractmethod
    async def execute(self, step: StepDefinition, ctx: PipelineContext) -> None:
        """Execute a pipeline step, reading from and writing to the context."""


class AgentStepExecutor(StepExecutor):
    """Runs a single PydanticAI agent. Used for spec_interpreter, auditor, etc."""

    async def execute(self, step: StepDefinition, ctx: PipelineContext) -> None:
        if step.agent is None:
            msg = f"Step '{step.id}' has type=agent but no 'agent' field"
            raise ValueError(msg)

        logger.info("Pipeline step '{step_id}': running agent '{agent}'", step_id=step.id, agent=step.agent)
        ctx.audit_trail.record(
            variable="",
            action=AuditAction.STEP_STARTED,
            agent=AgentName.ORCHESTRATOR,
            details={"step": step.id, "agent": step.agent},
        )

        # Import agent module and get the agent singleton
        from src.agents.factory import load_agent
        from src.config.llm_gateway import create_llm

        agent_config_path = f"config/agents/{step.agent}.yaml"
        agent = load_agent(agent_config_path)
        llm = create_llm(base_url=ctx.llm_base_url)

        # Build deps and prompt based on which agent this is
        # NOTE: For now, agent-specific dep building is dispatched by agent name.
        # This is a deliberate trade-off — full generalization would require a
        # deps factory registry, which is Phase 14.2 scope.
        deps, prompt = _build_agent_deps_and_prompt(step, ctx)
        result = await agent.run(prompt, deps=deps, model=llm)
        ctx.set_output(step.id, "result", result.output)

        ctx.audit_trail.record(
            variable="",
            action=AuditAction.STEP_COMPLETED,
            agent=step.agent,
            details={"step": step.id},
        )


class BuiltinStepExecutor(StepExecutor):
    """Runs a non-LLM Python function (build_dag, compare_outputs, export_adam)."""

    async def execute(self, step: StepDefinition, ctx: PipelineContext) -> None:
        if step.builtin is None:
            msg = f"Step '{step.id}' has type=builtin but no 'builtin' field"
            raise ValueError(msg)

        logger.info("Pipeline step '{step_id}': running builtin '{builtin}'", step_id=step.id, builtin=step.builtin)
        builtin_fn = BUILTIN_REGISTRY.get(step.builtin)
        if builtin_fn is None:
            msg = f"Unknown builtin '{step.builtin}'. Available: {list(BUILTIN_REGISTRY.keys())}"
            raise ValueError(msg)

        await builtin_fn(step, ctx)


class GatherStepExecutor(StepExecutor):
    """Runs N agents in parallel via asyncio.gather. Used for coder+QC."""

    async def execute(self, step: StepDefinition, ctx: PipelineContext) -> None:
        if not step.agents:
            msg = f"Step '{step.id}' has type=gather but no 'agents' list"
            raise ValueError(msg)

        logger.info(
            "Pipeline step '{step_id}': gathering {n} agents: {agents}",
            step_id=step.id,
            n=len(step.agents),
            agents=step.agents,
        )

        from src.agents.factory import load_agent
        from src.config.llm_gateway import create_llm

        llm = create_llm(base_url=ctx.llm_base_url)
        tasks = []
        for agent_name in step.agents:
            agent = load_agent(f"config/agents/{agent_name}.yaml")
            deps, prompt = _build_agent_deps_and_prompt(step, ctx, agent_name=agent_name)
            tasks.append(agent.run(prompt, deps=deps, model=llm))

        results = await asyncio.gather(*tasks)
        # Store each agent's output keyed by agent name
        for agent_name, result in zip(step.agents, results, strict=True):
            ctx.set_output(step.id, agent_name, result.output)


class HITLGateStepExecutor(StepExecutor):
    """Pauses the pipeline until human approval. Creates an asyncio.Event."""

    async def execute(self, step: StepDefinition, ctx: PipelineContext) -> None:
        message = str(step.config.get("message", "Awaiting human approval"))
        logger.info(
            "Pipeline step '{step_id}': HITL gate — {message}",
            step_id=step.id,
            message=message,
        )
        ctx.audit_trail.record(
            variable="",
            action=AuditAction.HITL_GATE_WAITING,
            agent=AgentName.ORCHESTRATOR,
            details={"step": step.id, "message": message},
        )

        # Store the event on the context so external callers (API) can set it
        approval_event = asyncio.Event()
        ctx.set_output(step.id, "_approval_event", approval_event)
        await approval_event.wait()

        ctx.audit_trail.record(
            variable="",
            action=AuditAction.HUMAN_APPROVED,
            agent=AgentName.HUMAN,
            details={"gate": step.id},
        )


class ParallelMapStepExecutor(StepExecutor):
    """Iterates over a collection (e.g., DAG layers) and runs sub_steps per item."""

    async def execute(self, step: StepDefinition, ctx: PipelineContext) -> None:
        if step.over != "dag_layers":
            msg = f"parallel_map only supports over='dag_layers', got '{step.over}'"
            raise ValueError(msg)
        if ctx.dag is None:
            msg = f"Step '{step.id}' requires ctx.dag but it is None"
            raise ValueError(msg)

        logger.info("Pipeline step '{step_id}': parallel_map over {over}", step_id=step.id, over=step.over)

        # Delegate to the existing derivation runner for each layer
        from src.engine.derivation_runner import run_variable

        layers = ctx.dag.layers
        for layer in layers:
            await asyncio.gather(*[
                run_variable(
                    variable=v,
                    dag=ctx.dag,
                    derived_df=ctx.derived_df,  # type: ignore[arg-type]  # checked above via ctx.dag
                    synthetic_csv=ctx.synthetic_csv,
                    llm_base_url=ctx.llm_base_url,
                )
                for v in layer
            ])


# --- Step Registry ---

STEP_EXECUTOR_REGISTRY: dict[StepType, StepExecutor] = {
    StepType.AGENT: AgentStepExecutor(),
    StepType.BUILTIN: BuiltinStepExecutor(),
    StepType.GATHER: GatherStepExecutor(),
    StepType.PARALLEL_MAP: ParallelMapStepExecutor(),
    StepType.HITL_GATE: HITLGateStepExecutor(),
}
```

**Also define the builtin registry and the `_build_agent_deps_and_prompt` helper.**

**Builtin registry** (at bottom of file):

```python
from typing import Any  # Any: heterogeneous callback signatures

# Builtin functions — each takes (step, ctx) and mutates ctx
async def _builtin_build_dag(step: StepDefinition, ctx: PipelineContext) -> None:
    """Build DerivationDAG from spec and available columns."""
    from src.domain.dag import DerivationDAG
    from src.domain.source_loader import get_source_columns

    if ctx.spec is None or ctx.derived_df is None:
        msg = f"Step '{step.id}' requires spec and derived_df in context"
        raise ValueError(msg)
    ctx.dag = DerivationDAG(ctx.spec.derivations, get_source_columns(ctx.derived_df))


async def _builtin_export_adam(step: StepDefinition, ctx: PipelineContext) -> None:
    """Export derived DataFrame as CSV and Parquet."""
    if ctx.derived_df is None or ctx.output_dir is None:
        return
    ctx.output_dir.mkdir(parents=True, exist_ok=True)
    wf_id = ctx.workflow_id
    ctx.derived_df.to_csv(ctx.output_dir / f"{wf_id}_adam.csv", index=False)
    formats = step.config.get("formats", ["csv"])
    if "parquet" in formats:  # type: ignore[operator]  # config value is str|int|float|bool|list[str]
        ctx.derived_df.to_parquet(ctx.output_dir / f"{wf_id}_adam.parquet", index=False, engine="pyarrow")


BUILTIN_REGISTRY: dict[str, Any] = {
    "build_dag": _builtin_build_dag,
    "export_adam": _builtin_export_adam,
}
```

**`_build_agent_deps_and_prompt` helper:**

```python
def _build_agent_deps_and_prompt(
    step: StepDefinition,
    ctx: PipelineContext,
    agent_name: str | None = None,
) -> tuple[Any, str]:
    """Build agent-specific deps and prompt based on agent name.

    This is a dispatch function — each agent has different dep requirements.
    """
    from src.agents.deps import AuditorDeps, CoderDeps, SpecInterpreterDeps

    name = agent_name or step.agent or ""

    if name == "spec_interpreter":
        if ctx.spec is None:
            msg = "spec_interpreter requires ctx.spec"
            raise ValueError(msg)
        deps = SpecInterpreterDeps(
            spec_yaml=str(ctx.spec),
            source_columns=list(ctx.derived_df.columns) if ctx.derived_df is not None else [],
        )
        return deps, "Interpret the transformation spec"

    if name == "auditor":
        if ctx.dag is None or ctx.spec is None:
            msg = "auditor requires ctx.dag and ctx.spec"
            raise ValueError(msg)
        dag_lines = [f"{v}: {ctx.dag.get_node(v).status}" for v in ctx.dag.execution_order]
        deps = AuditorDeps(
            dag_summary="\n".join(dag_lines),
            workflow_id=ctx.workflow_id,
            spec_metadata=ctx.spec.metadata,
        )
        return deps, "Generate audit summary"

    if name in ("coder", "qc_programmer"):
        if ctx.derived_df is None:
            msg = f"{name} requires ctx.derived_df"
            raise ValueError(msg)
        # For coder/QC, deps are built per-variable in derivation_runner, not here
        # This branch is a fallback — the ParallelMapStepExecutor delegates to run_variable
        msg = f"Agent '{name}' should be invoked via parallel_map, not directly"
        raise ValueError(msg)

    msg = f"No deps builder for agent '{name}'"
    raise ValueError(msg)
```

**Constraints:**
- `from __future__ import annotations` at top
- Heavy imports (agent modules, domain modules) go INSIDE methods, not at module top — this prevents circular imports and keeps the module importable without triggering agent loading
- Every executor validates its step configuration in the first lines (check for None fields) and raises `ValueError` with descriptive messages
- The `ParallelMapStepExecutor` delegates to the existing `run_variable` function — do NOT reimplement derivation logic
- `STEP_EXECUTOR_REGISTRY` maps `StepType` enum to executor instances (not classes)
- `BUILTIN_REGISTRY` maps string names to async functions
- Add `STEP_STARTED`, `STEP_COMPLETED`, `HITL_GATE_WAITING` to `AuditAction` enum — see "Files to Modify" section below
- File will be ~190 lines — acceptable since it contains 5 classes + 2 registries + 1 helper

**Reference:**
- `src/engine/derivation_runner.py` for the `run_variable` function signature
- `src/agents/factory.py` for `load_agent` usage
- `src/agents/deps.py` for dep dataclass constructors

---

### 4. `tests/unit/test_pipeline_models.py` (NEW)

**Purpose:** Tests for pipeline YAML parsing and model validation.

**Tests to write:**

```python
def test_load_pipeline_valid_yaml_returns_definition(tmp_path: Path) -> None:
    """Parse a valid pipeline YAML and verify all fields."""
    # Arrange — write a minimal pipeline YAML
    yaml_content = """
    pipeline:
      name: test_pipeline
      version: "1.0"
      steps:
        - id: step1
          type: agent
          agent: spec_interpreter
          description: "Parse spec"
        - id: step2
          type: builtin
          builtin: build_dag
          depends_on: [step1]
        - id: step3
          type: hitl_gate
          depends_on: [step2]
          config:
            message: "Review before audit"
    """
    yaml_path = tmp_path / "pipeline.yaml"
    yaml_path.write_text(yaml_content)

    # Act
    pipeline = load_pipeline(yaml_path)

    # Assert
    assert pipeline.name == "test_pipeline"
    assert len(pipeline.steps) == 3
    assert pipeline.steps[0].type == StepType.AGENT
    assert pipeline.steps[0].agent == "spec_interpreter"
    assert pipeline.steps[1].type == StepType.BUILTIN
    assert pipeline.steps[1].builtin == "build_dag"
    assert pipeline.steps[1].depends_on == ["step1"]
    assert pipeline.steps[2].type == StepType.HITL_GATE
    assert pipeline.steps[2].config["message"] == "Review before audit"


def test_load_pipeline_missing_file_raises_file_not_found() -> None:
    """Attempting to load a non-existent file raises FileNotFoundError."""
    # Act & Assert
    with pytest.raises(FileNotFoundError, match="Pipeline config not found"):
        load_pipeline("/nonexistent/pipeline.yaml")


def test_load_pipeline_gather_step_with_agents(tmp_path: Path) -> None:
    """Parse a gather step with multiple agents."""
    yaml_content = """
    pipeline:
      name: gather_test
      steps:
        - id: dual_code
          type: gather
          agents: [coder, qc_programmer]
    """
    yaml_path = tmp_path / "pipeline.yaml"
    yaml_path.write_text(yaml_content)

    # Act
    pipeline = load_pipeline(yaml_path)

    # Assert
    assert pipeline.steps[0].type == StepType.GATHER
    assert pipeline.steps[0].agents == ["coder", "qc_programmer"]


def test_load_pipeline_parallel_map_with_sub_steps(tmp_path: Path) -> None:
    """Parse a parallel_map step with nested sub_steps."""
    yaml_content = """
    pipeline:
      name: map_test
      steps:
        - id: derive
          type: parallel_map
          over: dag_layers
          sub_steps:
            - id: code_gen
              type: gather
              agents: [coder, qc_programmer]
            - id: verify
              type: builtin
              builtin: compare_outputs
    """
    yaml_path = tmp_path / "pipeline.yaml"
    yaml_path.write_text(yaml_content)

    # Act
    pipeline = load_pipeline(yaml_path)

    # Assert
    step = pipeline.steps[0]
    assert step.type == StepType.PARALLEL_MAP
    assert step.over == "dag_layers"
    assert step.sub_steps is not None
    assert len(step.sub_steps) == 2
    assert step.sub_steps[0].type == StepType.GATHER


def test_step_type_enum_values() -> None:
    """Verify StepType enum has all expected members."""
    assert StepType.AGENT == "agent"
    assert StepType.BUILTIN == "builtin"
    assert StepType.GATHER == "gather"
    assert StepType.PARALLEL_MAP == "parallel_map"
    assert StepType.HITL_GATE == "hitl_gate"
```

**Constraints:**
- `from __future__ import annotations` at top
- Use `tmp_path` fixture for YAML file creation
- AAA comments in every test
- Test names: `test_<action>_<scenario>_<expected>`
- Import `load_pipeline` and `StepType` from `src.domain.pipeline_models`
- `pytest.raises` with `match=` parameter (never bare)

**Reference:** `tests/unit/test_spec_parser.py` for YAML parsing test pattern

---

### 5. `tests/unit/test_step_executors.py` (NEW)

**Purpose:** Tests for step executors — mainly validation and error paths. Agent execution tests require LLM mocks (Phase 14.4).

**Tests to write:**

```python
def test_agent_executor_missing_agent_field_raises_value_error() -> None:
    """AgentStepExecutor raises ValueError if step has no agent field."""
    step = StepDefinition(id="bad", type=StepType.AGENT)  # no agent field
    executor = AgentStepExecutor()
    with pytest.raises(ValueError, match="no 'agent' field"):
        await executor.execute(step, mock_ctx)


def test_builtin_executor_unknown_builtin_raises_value_error() -> None:
    """BuiltinStepExecutor raises ValueError for unregistered builtin name."""
    step = StepDefinition(id="bad", type=StepType.BUILTIN, builtin="nonexistent")
    executor = BuiltinStepExecutor()
    with pytest.raises(ValueError, match="Unknown builtin 'nonexistent'"):
        await executor.execute(step, mock_ctx)


def test_builtin_executor_missing_builtin_field_raises_value_error() -> None:
    """BuiltinStepExecutor raises ValueError if step has no builtin field."""
    step = StepDefinition(id="bad", type=StepType.BUILTIN)
    executor = BuiltinStepExecutor()
    with pytest.raises(ValueError, match="no 'builtin' field"):
        await executor.execute(step, mock_ctx)


def test_gather_executor_missing_agents_raises_value_error() -> None:
    """GatherStepExecutor raises ValueError if step has no agents list."""
    step = StepDefinition(id="bad", type=StepType.GATHER)
    executor = GatherStepExecutor()
    with pytest.raises(ValueError, match="no 'agents' list"):
        await executor.execute(step, mock_ctx)


def test_parallel_map_unsupported_over_raises_value_error() -> None:
    """ParallelMapStepExecutor only supports over='dag_layers'."""
    step = StepDefinition(id="bad", type=StepType.PARALLEL_MAP, over="something_else")
    executor = ParallelMapStepExecutor()
    with pytest.raises(ValueError, match="only supports over='dag_layers'"):
        await executor.execute(step, mock_ctx)


def test_step_executor_registry_has_all_step_types() -> None:
    """STEP_EXECUTOR_REGISTRY covers every StepType enum member."""
    for step_type in StepType:
        assert step_type in STEP_EXECUTOR_REGISTRY, f"Missing executor for {step_type}"
```

**Fixture for mock context:**
```python
@pytest.fixture
def mock_ctx() -> PipelineContext:
    """Minimal PipelineContext for testing executor validation."""
    from src.audit.trail import AuditTrail
    return PipelineContext(
        workflow_id="test-wf",
        audit_trail=AuditTrail("test-wf"),
        llm_base_url="http://localhost:8650/v1",
    )
```

**Constraints:**
- All executor validation tests are async (executors are async)
- Use `pytest.raises(ValueError, match="...")` with specific patterns
- The `mock_ctx` fixture creates a real `AuditTrail` (lightweight, no DB)
- Do NOT test actual agent execution here (requires LLM) — only test validation/error paths

**Reference:** `tests/unit/test_agent_factory.py` for agent-related test patterns

---

## Files to Modify

### 6. `src/domain/models.py` (MODIFY)

**Change:** Add 3 new members to the `AuditAction` StrEnum for pipeline step tracking.

**Find the `AuditAction` class and add these members:**
```python
STEP_STARTED = "step_started"
STEP_COMPLETED = "step_completed"
HITL_GATE_WAITING = "hitl_gate_waiting"
```

**Add them AFTER the existing members** (after `HUMAN_APPROVED`).

**Constraints:**
- Do NOT reorder or remove existing members
- Do NOT modify any other class in this file

---

## After Implementation

1. Run: `uv run ruff check . --fix && uv run ruff format .`
2. Run: `uv run pyright .`
3. Run: `uv run lint-imports` — verify no layer violations (domain cannot import engine)
4. Run: `uv run pytest tests/unit/test_pipeline_models.py tests/unit/test_step_executors.py -v`
5. Run: `uv run pytest` — full suite, ensure no regressions
6. Verify file sizes: `wc -l src/domain/pipeline_models.py src/engine/pipeline_context.py src/engine/step_executors.py`
   - pipeline_models.py should be ~70 lines
   - pipeline_context.py should be ~60 lines
   - step_executors.py should be ~190 lines (acceptable for 5 classes + registries)
