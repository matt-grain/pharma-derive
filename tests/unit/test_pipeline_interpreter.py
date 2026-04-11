"""Unit tests for pipeline_interpreter: topological sort and YAML loading."""

from __future__ import annotations

import pytest

from src.domain.exceptions import CDDEError
from src.domain.pipeline_models import StepDefinition, StepType, load_pipeline
from src.engine.pipeline_interpreter import topological_sort


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
