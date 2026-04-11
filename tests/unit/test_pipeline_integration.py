"""Integration tests for the pipeline interpreter — validates step execution flow."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from src.audit.trail import AuditTrail
from src.domain.exceptions import CDDEError
from src.domain.pipeline_models import PipelineDefinition, StepDefinition, StepType
from src.engine.pipeline_context import PipelineContext
from src.engine.pipeline_interpreter import PipelineInterpreter


@pytest.fixture
def base_ctx(tmp_path: Path) -> PipelineContext:
    """Minimal context for integration tests."""
    return PipelineContext(
        workflow_id="integ-test",
        audit_trail=AuditTrail("integ-test"),
        llm_base_url="http://localhost:8650/v1",
        output_dir=tmp_path / "output",
    )


async def test_interpreter_runs_builtin_only_pipeline(base_ctx: PipelineContext, sample_spec_path: Path) -> None:
    """A pipeline with only builtin steps runs without errors."""
    # Arrange — seed spec path into context
    base_ctx.step_outputs["_init"] = {"spec_path": sample_spec_path}
    pipeline = PipelineDefinition(
        name="test",
        steps=[
            StepDefinition(id="parse_spec", type=StepType.BUILTIN, builtin="parse_spec"),
            StepDefinition(id="build_dag", type=StepType.BUILTIN, builtin="build_dag", depends_on=["parse_spec"]),
        ],
    )
    interpreter = PipelineInterpreter(pipeline, base_ctx)

    # Act
    await interpreter.run()

    # Assert
    assert base_ctx.spec is not None
    assert base_ctx.dag is not None
    assert base_ctx.derived_df is not None
    assert len(base_ctx.dag.execution_order) > 0


async def test_interpreter_stops_on_step_error(base_ctx: PipelineContext) -> None:
    """If a step fails, interpreter raises CDDEError and stops."""
    # Arrange — parse_spec without seeded spec_path will fail
    pipeline = PipelineDefinition(
        name="test_fail",
        steps=[
            StepDefinition(id="parse_spec", type=StepType.BUILTIN, builtin="parse_spec"),
        ],
    )
    interpreter = PipelineInterpreter(pipeline, base_ctx)

    # Act & Assert
    with pytest.raises(CDDEError, match="Step 'parse_spec' failed"):
        await interpreter.run()


async def test_interpreter_tracks_current_step(base_ctx: PipelineContext, sample_spec_path: Path) -> None:
    """current_step property reflects the running step."""
    # Arrange
    base_ctx.step_outputs["_init"] = {"spec_path": sample_spec_path}
    pipeline = PipelineDefinition(
        name="test_tracking",
        steps=[
            StepDefinition(id="parse_spec", type=StepType.BUILTIN, builtin="parse_spec"),
        ],
    )
    interpreter = PipelineInterpreter(pipeline, base_ctx)

    # Assert before
    assert interpreter.current_step is None

    # Act
    await interpreter.run()

    # Assert after
    assert interpreter.current_step is None  # finished


async def test_interpreter_export_creates_files(base_ctx: PipelineContext, sample_spec_path: Path) -> None:
    """Export step creates CSV file in output directory."""
    # Arrange
    base_ctx.step_outputs["_init"] = {"spec_path": sample_spec_path}
    pipeline = PipelineDefinition(
        name="test_export",
        steps=[
            StepDefinition(id="parse_spec", type=StepType.BUILTIN, builtin="parse_spec"),
            StepDefinition(
                id="export",
                type=StepType.BUILTIN,
                builtin="export_adam",
                depends_on=["parse_spec"],
                config={"formats": ["csv"]},
            ),
        ],
    )
    interpreter = PipelineInterpreter(pipeline, base_ctx)

    # Act
    await interpreter.run()

    # Assert
    assert base_ctx.output_dir is not None
    csv_path = base_ctx.output_dir / "integ-test_adam.csv"
    assert csv_path.exists()
