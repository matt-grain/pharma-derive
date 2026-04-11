"""Equivalence test: DerivationOrchestrator vs YAML PipelineInterpreter.

Runs both paths on the same spec (simple_mock) through the builtin steps
(parse_spec + build_dag + export) and verifies they produce identical
spec, DAG structure, source DataFrame, and output files.

LLM-dependent steps (derive_variables, audit) are excluded — they require
a running AgentLens mailbox and are not deterministic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from src.audit.trail import AuditTrail
from src.domain.dag import DerivationDAG
from src.domain.pipeline_models import PipelineDefinition, StepDefinition, StepType
from src.domain.source_loader import get_source_columns, load_source_data
from src.domain.spec_parser import parse_spec
from src.domain.synthetic import generate_synthetic
from src.engine.pipeline_context import PipelineContext
from src.engine.pipeline_interpreter import PipelineInterpreter

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Old path: reproduce what DerivationOrchestrator._step_spec_review +
# _step_build_dag do (without FSM transitions or LLM calls)
# ---------------------------------------------------------------------------


def _run_old_orchestrator_builtin_steps(spec_path: Path) -> tuple[pd.DataFrame, DerivationDAG, str]:
    """Execute the spec-review + dag-build steps the old way (hardcoded Python)."""
    spec = parse_spec(spec_path)
    source_df = load_source_data(spec)
    derived_df = source_df.copy()
    synthetic_csv = generate_synthetic(source_df, rows=spec.synthetic.rows).to_csv(index=False)
    dag = DerivationDAG(spec.derivations, get_source_columns(derived_df))
    return derived_df, dag, synthetic_csv


# ---------------------------------------------------------------------------
# New path: PipelineInterpreter with builtin steps
# ---------------------------------------------------------------------------


async def _run_new_pipeline_builtin_steps(
    spec_path: Path,
    output_dir: Path,
) -> PipelineContext:
    """Execute parse_spec + build_dag + export via the YAML pipeline interpreter."""
    ctx = PipelineContext(
        workflow_id="equiv-test",
        audit_trail=AuditTrail("equiv-test"),
        llm_base_url="http://localhost:8650/v1",
        output_dir=output_dir,
    )
    ctx.step_outputs["_init"] = {"spec_path": spec_path}

    pipeline = PipelineDefinition(
        name="equivalence_test",
        steps=[
            StepDefinition(id="parse_spec", type=StepType.BUILTIN, builtin="parse_spec"),
            StepDefinition(id="build_dag", type=StepType.BUILTIN, builtin="build_dag", depends_on=["parse_spec"]),
            StepDefinition(
                id="export",
                type=StepType.BUILTIN,
                builtin="export_adam",
                depends_on=["build_dag"],
                config={"formats": ["csv", "parquet"]},
            ),
        ],
    )
    interpreter = PipelineInterpreter(pipeline, ctx)
    await interpreter.run()
    return ctx


# ---------------------------------------------------------------------------
# Equivalence tests
# ---------------------------------------------------------------------------


async def test_spec_parsing_produces_identical_spec(sample_spec_path: Path, tmp_path: Path) -> None:
    """Both paths parse the same spec YAML and produce identical TransformationSpec."""
    # Arrange + Act — old path
    old_spec = parse_spec(sample_spec_path)

    # Act — new path
    ctx = await _run_new_pipeline_builtin_steps(sample_spec_path, tmp_path / "output")

    # Assert
    assert ctx.spec is not None
    assert ctx.spec.metadata.study == old_spec.metadata.study
    assert len(ctx.spec.derivations) == len(old_spec.derivations)
    for old_rule, new_rule in zip(old_spec.derivations, ctx.spec.derivations, strict=True):
        assert old_rule.variable == new_rule.variable
        assert old_rule.logic == new_rule.logic
        assert old_rule.source_columns == new_rule.source_columns


async def test_dag_structure_is_identical(sample_spec_path: Path, tmp_path: Path) -> None:
    """Both paths build DAGs with the same execution order, layers, and dependencies."""
    # Act — old path
    _, old_dag, _ = _run_old_orchestrator_builtin_steps(sample_spec_path)

    # Act — new path
    ctx = await _run_new_pipeline_builtin_steps(sample_spec_path, tmp_path / "output")

    # Assert
    assert ctx.dag is not None
    assert old_dag.execution_order == ctx.dag.execution_order
    assert len(old_dag.layers) == len(ctx.dag.layers)
    for old_layer, new_layer in zip(old_dag.layers, ctx.dag.layers, strict=True):
        assert sorted(old_layer) == sorted(new_layer)


async def test_source_dataframe_is_identical(sample_spec_path: Path, tmp_path: Path) -> None:
    """Both paths load and copy the same source DataFrame (columns + values)."""
    # Act — old path
    old_df, _, _ = _run_old_orchestrator_builtin_steps(sample_spec_path)

    # Act — new path
    ctx = await _run_new_pipeline_builtin_steps(sample_spec_path, tmp_path / "output")

    # Assert
    assert ctx.derived_df is not None
    assert list(old_df.columns) == list(ctx.derived_df.columns)
    assert len(old_df) == len(ctx.derived_df)
    pd.testing.assert_frame_equal(old_df, ctx.derived_df)


async def test_synthetic_csv_is_identical(sample_spec_path: Path, tmp_path: Path) -> None:
    """Both paths generate the same synthetic CSV string."""
    # Act — old path
    _, _, old_synthetic = _run_old_orchestrator_builtin_steps(sample_spec_path)

    # Act — new path
    ctx = await _run_new_pipeline_builtin_steps(sample_spec_path, tmp_path / "output")

    # Assert
    assert ctx.synthetic_csv == old_synthetic


async def test_export_produces_csv_and_parquet(sample_spec_path: Path, tmp_path: Path) -> None:
    """Pipeline export step creates both CSV and Parquet files."""
    # Act
    ctx = await _run_new_pipeline_builtin_steps(sample_spec_path, tmp_path / "output")

    # Assert
    output_dir = tmp_path / "output"
    assert (output_dir / "equiv-test_adam.csv").exists()
    assert (output_dir / "equiv-test_adam.parquet").exists()

    # Verify CSV content matches the DataFrame
    exported_df = pd.read_csv(output_dir / "equiv-test_adam.csv")
    assert ctx.derived_df is not None
    assert list(exported_df.columns) == list(ctx.derived_df.columns)
    assert len(exported_df) == len(ctx.derived_df)
