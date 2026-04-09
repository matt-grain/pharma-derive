"""Tests for src/engine/orchestrator.py — state wiring and non-LLM behaviour."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pandas as pd
import pytest

from src.domain.dag import DerivationDAG
from src.domain.spec_parser import get_source_columns, parse_spec
from src.engine.orchestrator import DerivationOrchestrator, WorkflowState, WorkflowStatus

if TYPE_CHECKING:
    from pathlib import Path

    from src.engine.workflow_fsm import WorkflowFSM

_MINIMAL_CSV = "patient_id,age,treatment_start,treatment_end,group\nP001,72,2024-01-15,2024-06-20,treatment\n"


@pytest.fixture
def orchestrator(sample_spec_path: Path) -> DerivationOrchestrator:
    return DerivationOrchestrator(spec_path=sample_spec_path)


def test_orchestrator_creates_with_fsm(orchestrator: DerivationOrchestrator) -> None:
    assert orchestrator.fsm.current_state_value == "created"


def test_orchestrator_creates_dag_from_spec(sample_spec_path: Path) -> None:
    spec = parse_spec(sample_spec_path)
    source_df = pd.read_csv(io.StringIO(_MINIMAL_CSV))
    source_cols = get_source_columns(source_df)

    dag = DerivationDAG(spec.derivations, source_cols)

    assert len(dag.nodes) == 4
    assert "AGE_GROUP" in dag.nodes
    assert "RISK_SCORE" in dag.nodes


def test_orchestrator_dag_layers(sample_spec_path: Path) -> None:
    spec = parse_spec(sample_spec_path)
    source_df = pd.read_csv(io.StringIO(_MINIMAL_CSV))
    dag = DerivationDAG(spec.derivations, get_source_columns(source_df))

    # simple_mock: AGE_GROUP + TREATMENT_DURATION in layer 0
    #              IS_ELDERLY in layer 1 (depends on AGE_GROUP)
    #              RISK_SCORE in layer 2 (depends on IS_ELDERLY + TREATMENT_DURATION)
    assert len(dag.layers) == 3


def test_workflow_status_is_strenum() -> None:
    assert WorkflowStatus.COMPLETED.value == "completed"
    assert WorkflowStatus.FAILED.value == "failed"


def test_workflow_state_accumulates_derived_columns() -> None:
    state = WorkflowState(workflow_id="test-123")
    df = pd.DataFrame({"age": [10, 20, 30]})
    state.derived_df = df
    state.derived_df["AGE_DOUBLE"] = df["age"] * 2

    assert "AGE_DOUBLE" in state.derived_df.columns
    assert state.derived_df["AGE_DOUBLE"].tolist() == [20, 40, 60]


def test_orchestrator_handles_nonexistent_spec_path() -> None:
    orch = DerivationOrchestrator(spec_path="/nonexistent/path/spec.yaml")
    fsm: WorkflowFSM = orch.fsm

    assert fsm.current_state_value == "created"
    assert orch.state.errors == []


def test_fsm_workflow_id_matches_state(orchestrator: DerivationOrchestrator) -> None:
    assert orchestrator.fsm.workflow_id == orchestrator.state.workflow_id
