"""Unit tests for pipeline_interpreter: topological sort and YAML loading."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.audit.trail import AuditTrail
from src.domain.exceptions import CDDEError
from src.domain.pipeline_models import PipelineDefinition, StepDefinition, StepType, load_pipeline
from src.engine.pipeline_context import PipelineContext
from src.engine.pipeline_fsm import PipelineFSM
from src.engine.pipeline_interpreter import PipelineInterpreter, topological_sort


def test_topological_sort_linear_chain_preserves_order() -> None:
    """Steps with linear depends_on are sorted in dependency order."""
    # Arrange
    steps = [
        StepDefinition(id="c", type=StepType.BUILTIN, builtin="x", depends_on=["b"]),
        StepDefinition(id="a", type=StepType.BUILTIN, builtin="x"),
        StepDefinition(id="b", type=StepType.BUILTIN, builtin="x", depends_on=["a"]),
    ]

    # Act
    result = topological_sort(steps)

    # Assert
    ids = [s.id for s in result]
    assert ids == ["a", "b", "c"]


def test_topological_sort_parallel_steps_sorted_alphabetically() -> None:
    """Steps with no dependencies between them are sorted alphabetically (deterministic)."""
    # Arrange
    steps = [
        StepDefinition(id="z", type=StepType.BUILTIN, builtin="x"),
        StepDefinition(id="a", type=StepType.BUILTIN, builtin="x"),
        StepDefinition(id="m", type=StepType.BUILTIN, builtin="x"),
    ]

    # Act
    result = topological_sort(steps)

    # Assert
    ids = [s.id for s in result]
    assert ids == ["a", "m", "z"]


def test_topological_sort_cycle_raises_cdde_error() -> None:
    """Circular dependencies raise CDDEError."""
    # Arrange
    steps = [
        StepDefinition(id="a", type=StepType.BUILTIN, builtin="x", depends_on=["b"]),
        StepDefinition(id="b", type=StepType.BUILTIN, builtin="x", depends_on=["a"]),
    ]

    # Act & Assert
    with pytest.raises(CDDEError, match="circular dependencies"):
        topological_sort(steps)


def test_topological_sort_unknown_dependency_raises_cdde_error() -> None:
    """Reference to non-existent step raises CDDEError."""
    # Arrange
    steps = [
        StepDefinition(id="a", type=StepType.BUILTIN, builtin="x", depends_on=["nonexistent"]),
    ]

    # Act & Assert
    with pytest.raises(CDDEError, match="unknown step 'nonexistent'"):
        topological_sort(steps)


def test_load_default_pipeline_parses_without_error() -> None:
    """The default clinical_derivation.yaml pipeline parses successfully."""
    # Act
    pipeline = load_pipeline("config/pipelines/clinical_derivation.yaml")

    # Assert
    assert pipeline.name == "clinical_derivation"
    assert len(pipeline.steps) == 6
    step_ids = [s.id for s in pipeline.steps]
    assert "parse_spec" in step_ids
    assert "human_review" in step_ids
    assert "export" in step_ids


async def test_interpreter_advances_fsm_per_step() -> None:
    """FSM receives advance() for each step ID in execution order."""
    # Arrange
    steps = [
        StepDefinition(id="first", type=StepType.BUILTIN, builtin="noop"),
        StepDefinition(id="second", type=StepType.BUILTIN, builtin="noop", depends_on=["first"]),
    ]
    pipeline = PipelineDefinition(name="test_pipeline", steps=steps)
    ctx = PipelineContext(workflow_id="test-wf", audit_trail=AuditTrail("test-wf"), llm_base_url="")
    fsm = PipelineFSM("test-wf", [s.id for s in steps])

    states_seen: list[str] = []
    original_advance = fsm.advance

    def tracking_advance(step_id: str) -> None:
        states_seen.append(step_id)
        original_advance(step_id)

    fsm.advance = tracking_advance  # type: ignore[method-assign]

    interpreter = PipelineInterpreter(pipeline, ctx, fsm)

    # Act — patch executor registry so no real builtin logic runs
    noop_executor = AsyncMock()
    noop_executor.execute = AsyncMock()
    with patch(
        "src.engine.pipeline_interpreter.PipelineInterpreter._execute_step",
        new=AsyncMock(),
    ):
        await interpreter.run()

    # Assert
    assert states_seen == ["first", "second"]
    assert fsm.current_state_value == "second"


async def test_interpreter_invokes_on_step_complete_for_every_step() -> None:
    """Checkpoint callback is awaited once per step with the step id in execution order."""
    # Arrange
    steps = [
        StepDefinition(id="first", type=StepType.BUILTIN, builtin="noop"),
        StepDefinition(id="second", type=StepType.BUILTIN, builtin="noop", depends_on=["first"]),
    ]
    pipeline = PipelineDefinition(name="test_pipeline", steps=steps)
    ctx = PipelineContext(workflow_id="test-wf", audit_trail=AuditTrail("test-wf"), llm_base_url="")
    interpreter = PipelineInterpreter(pipeline, ctx)

    checkpointed: list[str] = []

    async def record_checkpoint(step_id: str) -> None:
        checkpointed.append(step_id)

    # Act
    with patch(
        "src.engine.pipeline_interpreter.PipelineInterpreter._execute_step",
        new=AsyncMock(),
    ):
        await interpreter.run(on_step_complete=record_checkpoint)

    # Assert
    assert checkpointed == ["first", "second"]


async def test_interpreter_without_fsm_runs_successfully() -> None:
    """Interpreter with fsm=None completes without error (backward compatibility)."""
    # Arrange
    steps = [StepDefinition(id="only", type=StepType.BUILTIN, builtin="noop")]
    pipeline = PipelineDefinition(name="test_pipeline", steps=steps)
    ctx = PipelineContext(workflow_id="test-wf", audit_trail=AuditTrail("test-wf"), llm_base_url="")
    interpreter = PipelineInterpreter(pipeline, ctx)  # fsm=None by default

    # Act & Assert — no AttributeError on None.advance()
    with patch(
        "src.engine.pipeline_interpreter.PipelineInterpreter._execute_step",
        new=AsyncMock(),
    ):
        await interpreter.run()  # must not raise
