"""Tests for src/engine/orchestrator.py — state wiring and non-LLM behaviour."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pandas as pd
import pytest

from src.domain.dag import DerivationDAG
from src.domain.models import WorkflowStatus
from src.domain.source_loader import get_source_columns
from src.domain.spec_parser import parse_spec
from src.engine.orchestrator import DerivationOrchestrator
from src.engine.workflow_models import WorkflowState

if TYPE_CHECKING:
    from pathlib import Path

    from src.engine.workflow_fsm import WorkflowFSM

_MINIMAL_CSV = "patient_id,age,treatment_start,treatment_end,group\nP001,72,2024-01-15,2024-06-20,treatment\n"


@pytest.fixture
def orchestrator(sample_spec_path: Path) -> DerivationOrchestrator:
    return DerivationOrchestrator(spec_path=sample_spec_path)


def test_orchestrator_creates_with_fsm(orchestrator: DerivationOrchestrator) -> None:
    # Act & Assert
    assert orchestrator.fsm.current_state_value == "created"


def test_orchestrator_creates_dag_from_spec(sample_spec_path: Path) -> None:
    # Arrange
    spec = parse_spec(sample_spec_path)
    source_df = pd.read_csv(io.StringIO(_MINIMAL_CSV))
    source_cols = get_source_columns(source_df)

    # Act
    dag = DerivationDAG(spec.derivations, source_cols)

    # Assert
    assert len(dag.nodes) == 4
    assert "AGE_GROUP" in dag.nodes
    assert "RISK_SCORE" in dag.nodes


def test_orchestrator_dag_layers(sample_spec_path: Path) -> None:
    # Arrange
    spec = parse_spec(sample_spec_path)
    source_df = pd.read_csv(io.StringIO(_MINIMAL_CSV))

    # Act
    dag = DerivationDAG(spec.derivations, get_source_columns(source_df))

    # Assert — simple_mock: AGE_GROUP + TREATMENT_DURATION in layer 0,
    #          IS_ELDERLY in layer 1, RISK_SCORE in layer 2
    assert len(dag.layers) == 3


def test_workflow_status_is_strenum() -> None:
    # Act & Assert
    assert WorkflowStatus.COMPLETED.value == "completed"
    assert WorkflowStatus.FAILED.value == "failed"


def test_workflow_state_accumulates_derived_columns() -> None:
    # Arrange
    state = WorkflowState(workflow_id="test-123")
    df = pd.DataFrame({"age": [10, 20, 30]})
    state.derived_df = df

    # Act
    state.derived_df["AGE_DOUBLE"] = df["age"] * 2

    # Assert
    assert "AGE_DOUBLE" in state.derived_df.columns
    assert state.derived_df["AGE_DOUBLE"].tolist() == [20, 40, 60]


def test_orchestrator_handles_nonexistent_spec_path() -> None:
    # Act
    orch = DerivationOrchestrator(spec_path="/nonexistent/path/spec.yaml")
    fsm: WorkflowFSM = orch.fsm

    # Assert
    assert fsm.current_state_value == "created"
    assert orch.state.errors == []


def test_fsm_workflow_id_matches_state(orchestrator: DerivationOrchestrator) -> None:
    # Act & Assert
    assert orchestrator.fsm.workflow_id == orchestrator.state.workflow_id
