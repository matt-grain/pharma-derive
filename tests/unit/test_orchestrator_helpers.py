"""Tests for src/engine/orchestrator_helpers.py — serialization and result building."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from src.domain.models import (
    DAGNode,
    DerivationRule,
    DerivationStatus,
    OutputDType,
    QCVerdict,
)
from src.domain.workflow_fsm import WorkflowFSM
from src.domain.workflow_models import WorkflowState, WorkflowStatus
from src.engine.orchestrator_helpers import (
    build_derivation_details,
    build_workflow_result,
    serialize_workflow_state,
)

if TYPE_CHECKING:
    from src.domain.dag import DerivationDAG


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_rule(variable: str = "AGE_GROUP") -> DerivationRule:
    return DerivationRule(
        variable=variable,
        source_columns=["age"],
        logic="If age >= 65: 'senior'.",
        output_type=OutputDType.STR,
    )


def _make_fsm_completed() -> WorkflowFSM:
    fsm = WorkflowFSM(workflow_id="test-completed")
    fsm.start_spec_review()
    fsm.finish_spec_review()
    fsm.start_deriving()
    fsm.start_verifying()
    fsm.finish_review_from_verify()
    fsm.start_auditing()
    fsm.finish()
    return fsm


def _make_fsm_failed() -> WorkflowFSM:
    fsm = WorkflowFSM(workflow_id="test-failed")
    fsm.start_spec_review()
    fsm.fail("simulated error")
    return fsm


# ---------------------------------------------------------------------------
# serialize_workflow_state
# ---------------------------------------------------------------------------


def test_serialize_workflow_state_with_dag_includes_nodes(
    sample_dag: DerivationDAG,
    sample_spec: object,
) -> None:
    # Arrange
    state = WorkflowState(workflow_id="wf-dag-test")
    state.dag = sample_dag
    state.spec = sample_spec  # type: ignore[assignment]

    # Act
    result_json = serialize_workflow_state(state, "verifying")
    data = json.loads(result_json)

    # Assert — every DAG variable appears in dag_nodes
    assert "dag_nodes" in data
    assert len(data["dag_nodes"]) == len(sample_dag.execution_order)
    for var in sample_dag.execution_order:
        assert var in data["dag_nodes"]


def test_serialize_workflow_state_without_dag_returns_empty_nodes() -> None:
    # Arrange
    state = WorkflowState(workflow_id="wf-no-dag")
    assert state.dag is None

    # Act
    result_json = serialize_workflow_state(state, "created")
    data = json.loads(result_json)

    # Assert
    assert data["dag_nodes"] == {}
    assert data["derived_variables"] == []


# ---------------------------------------------------------------------------
# build_workflow_result
# ---------------------------------------------------------------------------


def test_build_workflow_result_completed_status() -> None:
    from src.audit.trail import AuditTrail

    # Arrange
    fsm = _make_fsm_completed()
    state = WorkflowState(workflow_id=fsm.workflow_id)
    audit_trail = AuditTrail(fsm.workflow_id)

    # Act
    result = build_workflow_result(state, fsm, audit_trail, elapsed=1.5)

    # Assert
    assert result.status == WorkflowStatus.COMPLETED
    assert result.workflow_id == fsm.workflow_id
    assert result.duration_seconds == 1.5


def test_build_workflow_result_failed_status() -> None:
    from src.audit.trail import AuditTrail

    # Arrange
    fsm = _make_fsm_failed()
    state = WorkflowState(workflow_id=fsm.workflow_id)
    audit_trail = AuditTrail(fsm.workflow_id)

    # Act
    result = build_workflow_result(state, fsm, audit_trail, elapsed=0.3)

    # Assert
    assert result.status == WorkflowStatus.FAILED


# ---------------------------------------------------------------------------
# build_derivation_details
# ---------------------------------------------------------------------------


def test_build_derivation_details_match_resolution() -> None:
    # Arrange
    node = DAGNode(
        rule=_make_rule(),
        status=DerivationStatus.APPROVED,
        qc_verdict=QCVerdict.MATCH,
        coder_code="return df['age'].apply(lambda x: 'senior' if x >= 65 else 'adult')",
        approved_code="return df['age'].apply(lambda x: 'senior' if x >= 65 else 'adult')",
    )

    # Act
    details = build_derivation_details(node)

    # Assert
    assert details["qc_verdict"] == QCVerdict.MATCH.value
    assert details["resolution"] == "QC match — coder version auto-approved"


def test_build_derivation_details_mismatch_debugger_resolution() -> None:
    # Arrange — MISMATCH where debugger approved the coder version
    coder_code = "return df['age'].apply(lambda x: 'senior' if x >= 65 else 'adult')"
    node = DAGNode(
        rule=_make_rule(),
        status=DerivationStatus.APPROVED,
        qc_verdict=QCVerdict.MISMATCH,
        coder_code=coder_code,
        qc_code="return df['age'].map(lambda x: 'senior' if x >= 65 else 'junior')",
        approved_code=coder_code,  # same as coder → "coder version approved"
        debug_analysis="Coder correctly handles edge case; QC missed the null branch.",
    )

    # Act
    details = build_derivation_details(node)

    # Assert
    assert details["qc_verdict"] == QCVerdict.MISMATCH.value
    assert details["resolution"] == "debugger resolved — coder version approved"
    assert details["debug_root_cause"] == "Coder correctly handles edge case; QC missed the null branch."
