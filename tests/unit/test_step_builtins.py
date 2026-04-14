"""Unit tests for step_builtins — BUILTIN_REGISTRY functions and build_agent_deps_and_prompt.

The builtin functions are private, but they are the sole content of BUILTIN_REGISTRY,
which is the module's public dispatch interface. Testing via the registry is equivalent
to testing the public API.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
import pytest

from src.audit.trail import AuditTrail
from src.engine.pipeline_context import PipelineContext
from src.engine.step_builtins import (
    AGENT_DEPS_BUILDERS,
    BUILTIN_REGISTRY,
    build_agent_deps_and_prompt,
)

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(workflow_id: str = "wf-test", output_dir: Path | None = None) -> PipelineContext:
    return PipelineContext(
        workflow_id=workflow_id,
        audit_trail=AuditTrail(workflow_id),
        llm_base_url="http://localhost:4010",
        output_dir=output_dir,
    )


def _minimal_step(step_id: str) -> object:
    """Return a StepDefinition with the given id and an empty config."""
    from src.domain.pipeline_models import StepDefinition, StepType

    return StepDefinition(id=step_id, type=StepType.BUILTIN, builtin=step_id)


# ---------------------------------------------------------------------------
# BUILTIN_REGISTRY completeness
# ---------------------------------------------------------------------------


def test_builtin_registry_contains_expected_keys() -> None:
    """BUILTIN_REGISTRY exposes all three expected builtin names."""
    # Act & Assert
    assert "parse_spec" in BUILTIN_REGISTRY
    assert "build_dag" in BUILTIN_REGISTRY
    assert "export_adam" in BUILTIN_REGISTRY


def test_builtin_registry_values_are_callable() -> None:
    """Every entry in BUILTIN_REGISTRY is an async callable."""
    import inspect

    for name, fn in BUILTIN_REGISTRY.items():
        assert callable(fn), f"Registry entry '{name}' is not callable"
        assert inspect.iscoroutinefunction(fn), f"Registry entry '{name}' is not async"


# ---------------------------------------------------------------------------
# parse_spec builtin
# ---------------------------------------------------------------------------


async def test_builtin_parse_spec_populates_context(sample_spec_path: Path) -> None:
    """parse_spec reads spec_path from _init context, populates ctx.spec and ctx.derived_df."""
    # Arrange
    ctx = _make_ctx()
    ctx.set_output("_init", "spec_path", str(sample_spec_path))
    step = _minimal_step("parse_spec")

    # Act
    await BUILTIN_REGISTRY["parse_spec"](step, ctx)

    # Assert
    assert ctx.spec is not None
    assert ctx.derived_df is not None
    assert ctx.synthetic_csv != ""


async def test_builtin_parse_spec_missing_init_raises_value_error() -> None:
    """parse_spec raises ValueError when _init.spec_path is absent from context."""
    # Arrange
    ctx = _make_ctx()  # no _init output at all
    step = _minimal_step("parse_spec")

    # Act & Assert
    with pytest.raises(ValueError, match=r"_init\.spec_path"):
        await BUILTIN_REGISTRY["parse_spec"](step, ctx)


async def test_builtin_parse_spec_missing_spec_path_key_raises_value_error() -> None:
    """parse_spec raises ValueError when _init exists but spec_path key is absent."""
    # Arrange
    ctx = _make_ctx()
    ctx.set_output("_init", "other_key", "irrelevant")
    step = _minimal_step("parse_spec")

    # Act & Assert
    with pytest.raises(ValueError, match=r"_init\.spec_path"):
        await BUILTIN_REGISTRY["parse_spec"](step, ctx)


async def test_builtin_parse_spec_writes_source_snapshot_to_output_dir(
    sample_spec_path: Path,
    tmp_path: Path,
) -> None:
    """parse_spec writes {workflow_id}_source.csv to output_dir with the loaded source data."""
    # Arrange
    wf_id = "wf-snapshot-001"
    ctx = _make_ctx(workflow_id=wf_id, output_dir=tmp_path / "output")
    ctx.set_output("_init", "spec_path", str(sample_spec_path))
    step = _minimal_step("parse_spec")

    # Act
    await BUILTIN_REGISTRY["parse_spec"](step, ctx)

    # Assert — snapshot file exists with the same rows as derived_df
    snapshot_path = tmp_path / "output" / f"{wf_id}_source.csv"
    assert snapshot_path.exists(), f"Expected SDTM snapshot at {snapshot_path}"
    assert ctx.derived_df is not None  # type guard
    snapshot_df = pd.read_csv(snapshot_path)
    assert len(snapshot_df) == len(ctx.derived_df)
    assert list(snapshot_df.columns) == list(ctx.derived_df.columns)


async def test_builtin_parse_spec_skips_snapshot_when_output_dir_is_none(
    sample_spec_path: Path,
    tmp_path: Path,
) -> None:
    """parse_spec does not crash and writes no file when output_dir is None."""
    # Arrange
    ctx = _make_ctx(output_dir=None)  # output_dir unset
    ctx.set_output("_init", "spec_path", str(sample_spec_path))
    step = _minimal_step("parse_spec")

    # Act — must not raise
    await BUILTIN_REGISTRY["parse_spec"](step, ctx)

    # Assert — ctx is still populated normally, no stray CSVs in tmp_path
    assert ctx.spec is not None
    assert ctx.derived_df is not None
    assert list(tmp_path.glob("*_source.csv")) == []


# ---------------------------------------------------------------------------
# build_dag builtin
# ---------------------------------------------------------------------------


async def test_builtin_build_dag_populates_context(sample_spec_path: Path) -> None:
    """build_dag builds DerivationDAG and stores it on ctx.dag."""
    # Arrange
    ctx = _make_ctx()
    ctx.set_output("_init", "spec_path", str(sample_spec_path))
    step = _minimal_step("build_dag")
    await BUILTIN_REGISTRY["parse_spec"](step, ctx)  # populate ctx.spec + ctx.derived_df

    # Act
    await BUILTIN_REGISTRY["build_dag"](step, ctx)

    # Assert
    assert ctx.dag is not None
    assert len(ctx.dag.execution_order) > 0


async def test_builtin_build_dag_missing_spec_raises_value_error() -> None:
    """build_dag raises ValueError when ctx.spec is None."""
    # Arrange
    ctx = _make_ctx()  # spec is None, derived_df is None
    step = _minimal_step("build_dag")

    # Act & Assert
    with pytest.raises(ValueError, match="requires spec and derived_df"):
        await BUILTIN_REGISTRY["build_dag"](step, ctx)


async def test_builtin_build_dag_missing_derived_df_raises_value_error(
    sample_spec_path: Path,
) -> None:
    """build_dag raises ValueError when ctx.derived_df is None even if spec is set."""
    # Arrange
    ctx = _make_ctx()
    ctx.set_output("_init", "spec_path", str(sample_spec_path))
    await BUILTIN_REGISTRY["parse_spec"](_minimal_step("parse_spec"), ctx)
    ctx.derived_df = None  # simulate missing derived_df
    step = _minimal_step("build_dag")

    # Act & Assert
    with pytest.raises(ValueError, match="requires spec and derived_df"):
        await BUILTIN_REGISTRY["build_dag"](step, ctx)


# ---------------------------------------------------------------------------
# export_adam builtin
# ---------------------------------------------------------------------------


async def test_builtin_export_adam_creates_csv(tmp_path: Path) -> None:
    """export_adam writes a CSV file named <workflow_id>_adam.csv to output_dir."""
    # Arrange
    wf_id = "run-001"
    ctx = _make_ctx(workflow_id=wf_id, output_dir=tmp_path / "output")
    ctx.derived_df = pd.DataFrame({"patient_id": ["P001", "P002"], "age": [45, 72]})
    step = _minimal_step("export_adam")

    # Act
    await BUILTIN_REGISTRY["export_adam"](step, ctx)

    # Assert
    expected = tmp_path / "output" / f"{wf_id}_adam.csv"
    assert expected.exists(), f"Expected CSV at {expected}"
    content = expected.read_text()
    assert "patient_id" in content
    assert "P001" in content


async def test_builtin_export_adam_creates_output_dir_if_missing(tmp_path: Path) -> None:
    """export_adam creates the output directory when it does not yet exist."""
    # Arrange
    output_dir = tmp_path / "nested" / "output"
    ctx = _make_ctx(workflow_id="wf-mkdir", output_dir=output_dir)
    ctx.derived_df = pd.DataFrame({"x": [1]})
    step = _minimal_step("export_adam")

    # Act
    await BUILTIN_REGISTRY["export_adam"](step, ctx)

    # Assert
    assert output_dir.exists()
    assert (output_dir / "wf-mkdir_adam.csv").exists()


async def test_builtin_export_adam_noop_when_derived_df_is_none(tmp_path: Path) -> None:
    """export_adam silently skips when ctx.derived_df is None."""
    # Arrange
    ctx = _make_ctx(output_dir=tmp_path)
    ctx.derived_df = None  # not set
    step = _minimal_step("export_adam")

    # Act — should not raise
    await BUILTIN_REGISTRY["export_adam"](step, ctx)

    # Assert — no CSV written
    csv_files = list(tmp_path.glob("*.csv"))
    assert csv_files == []


async def test_builtin_export_adam_noop_when_output_dir_is_none() -> None:
    """export_adam silently skips when ctx.output_dir is None."""
    # Arrange
    ctx = _make_ctx(output_dir=None)
    ctx.derived_df = pd.DataFrame({"x": [1]})
    step = _minimal_step("export_adam")

    # Act & Assert — no exception raised
    await BUILTIN_REGISTRY["export_adam"](step, ctx)


# ---------------------------------------------------------------------------
# build_agent_deps_and_prompt — public function
# ---------------------------------------------------------------------------


def test_build_agent_deps_and_prompt_unknown_agent_raises_value_error() -> None:
    """build_agent_deps_and_prompt raises ValueError for completely unregistered agent names."""
    # Arrange
    from src.domain.pipeline_models import StepDefinition, StepType

    ctx = _make_ctx()
    step = StepDefinition(id="s", type=StepType.AGENT, agent="ghost_agent")

    # Act & Assert
    with pytest.raises(ValueError, match="No deps builder for agent 'ghost_agent'"):
        build_agent_deps_and_prompt(step, ctx, agent_name="ghost_agent")


def test_build_agent_deps_and_prompt_parallel_map_only_agent_raises_value_error() -> None:
    """Agents in _PARALLEL_MAP_ONLY_AGENTS raise ValueError with a clear message."""
    # Arrange
    from src.domain.pipeline_models import StepDefinition, StepType

    ctx = _make_ctx()
    step = StepDefinition(id="s", type=StepType.AGENT, agent="coder")

    # Act & Assert
    with pytest.raises(ValueError, match="parallel_map"):
        build_agent_deps_and_prompt(step, ctx, agent_name="coder")


def test_build_agent_deps_and_prompt_spec_interpreter_requires_spec() -> None:
    """spec_interpreter builder raises ValueError when ctx.spec is None."""
    # Arrange
    from src.domain.pipeline_models import StepDefinition, StepType

    ctx = _make_ctx()  # spec is None
    step = StepDefinition(id="s", type=StepType.AGENT, agent="spec_interpreter")

    # Act & Assert
    with pytest.raises(ValueError, match=r"spec_interpreter requires ctx\.spec"):
        build_agent_deps_and_prompt(step, ctx, agent_name="spec_interpreter")


def test_build_agent_deps_and_prompt_agent_name_falls_back_to_step_agent_field() -> None:
    """When agent_name is None, the step's agent field is used for dispatch."""
    # Arrange
    from src.domain.pipeline_models import StepDefinition, StepType

    ctx = _make_ctx()
    step = StepDefinition(id="s", type=StepType.AGENT, agent="ghost")

    # Act & Assert — same error as explicit ghost_agent, proving field fallback works
    with pytest.raises(ValueError, match="No deps builder for agent 'ghost'"):
        build_agent_deps_and_prompt(step, ctx)  # agent_name not passed


def test_agent_deps_builders_contains_expected_keys() -> None:
    """AGENT_DEPS_BUILDERS exposes at least spec_interpreter and auditor."""
    # Act & Assert
    assert "spec_interpreter" in AGENT_DEPS_BUILDERS
    assert "auditor" in AGENT_DEPS_BUILDERS
