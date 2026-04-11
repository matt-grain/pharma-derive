"""Unit tests for pipeline YAML parsing and model validation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from src.domain.pipeline_models import StepType, load_pipeline


def test_load_pipeline_valid_yaml_returns_definition(tmp_path: Path) -> None:
    """Parse a valid pipeline YAML and verify all fields."""
    # Arrange
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
    # Arrange
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
    # Arrange
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
    # Act & Assert
    assert StepType.AGENT == "agent"
    assert StepType.BUILTIN == "builtin"
    assert StepType.GATHER == "gather"
    assert StepType.PARALLEL_MAP == "parallel_map"
    assert StepType.HITL_GATE == "hitl_gate"
