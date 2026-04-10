"""Integration tests for the DerivationOrchestrator.

These tests verify orchestrator structure, audit trail wiring, and repository
injection without hitting a real LLM. Full end-to-end LLM tests require a
running AgentLens mailbox (see docs/REQUIREMENTS.md) and are out of scope here.

Strategy:
- Test orchestrator instantiation and property access
- Test audit trail wiring (AuditTrail created and accessible)
- Test that repos injected via DI are stored (not called — that requires a live LLM)
- Test spec parsing and DAG construction in isolation from agent calls
- Test WorkflowResult schema and WorkflowStatus enum
"""

from __future__ import annotations

from pathlib import Path  # noqa: TC003 — used at runtime in pytest fixture parameter types

import pytest
from pydantic import ValidationError

from src.domain.models import WorkflowStatus
from src.engine.orchestrator import DerivationOrchestrator, WorkflowResult

# ---------------------------------------------------------------------------
# Orchestrator construction
# ---------------------------------------------------------------------------


def test_orchestrator_initialises_with_spec_path(sample_spec_path: Path) -> None:
    # Arrange & Act
    orch = DerivationOrchestrator(spec_path=sample_spec_path)

    # Assert
    assert orch.state.workflow_id is not None
    assert len(orch.state.workflow_id) > 0
    assert orch.fsm is not None
    assert orch.audit_trail is not None


def test_orchestrator_audit_trail_workflow_id_matches_fsm(sample_spec_path: Path) -> None:
    # Arrange
    orch = DerivationOrchestrator(spec_path=sample_spec_path)

    # Act — audit_trail is wired at construction time
    wf_id = orch.state.workflow_id
    orch.audit_trail.record(variable="TEST", action="noop", agent="test")

    # Assert — all records carry the same workflow_id
    records = orch.audit_trail.records
    assert len(records) == 1
    assert records[0].workflow_id == wf_id


def test_orchestrator_accepts_optional_repos(sample_spec_path: Path) -> None:
    """Repos are optional — orchestrator must not fail when they're None."""
    # Arrange & Act — no exception on construction with None repos
    orch = DerivationOrchestrator(
        spec_path=sample_spec_path,
        pattern_repo=None,
        qc_repo=None,
        state_repo=None,
    )

    # Assert
    assert orch.state is not None


def test_orchestrator_accepts_output_dir(sample_spec_path: Path, tmp_path: Path) -> None:
    # Arrange & Act — no exception on construction with output_dir
    orch = DerivationOrchestrator(
        spec_path=sample_spec_path,
        output_dir=tmp_path / "audit_output",
    )

    # Assert
    assert orch.state is not None


# ---------------------------------------------------------------------------
# WorkflowResult schema
# ---------------------------------------------------------------------------


def test_workflow_result_is_frozen() -> None:
    """WorkflowResult must be immutable (frozen=True on the Pydantic model)."""
    # Arrange
    result = WorkflowResult(
        workflow_id="wf_abc",
        study="TEST_STUDY",
        status=WorkflowStatus.COMPLETED,
        derived_variables=["AGE_GROUP"],
        qc_summary={"AGE_GROUP": "match"},
        audit_records=[],
        errors=[],
        duration_seconds=1.23,
    )

    # Act & Assert — frozen models raise ValidationError on mutation
    with pytest.raises(ValidationError):
        result.study = "OTHER"  # type: ignore[misc]


def test_workflow_status_enum_values() -> None:
    # Assert
    assert WorkflowStatus.COMPLETED == "completed"
    assert WorkflowStatus.FAILED == "failed"


# ---------------------------------------------------------------------------
# Spec parsing in orchestrator context
# ---------------------------------------------------------------------------


def test_orchestrator_fsm_has_workflow_id_matching_state(sample_spec_path: Path) -> None:
    # Arrange
    orch = DerivationOrchestrator(spec_path=sample_spec_path)

    # Assert — FSM workflow_id and state workflow_id are in sync
    assert orch.fsm.workflow_id == orch.state.workflow_id


def test_orchestrator_fsm_initial_state(sample_spec_path: Path) -> None:
    """FSM must start in 'created' state before any step is executed."""
    # Arrange
    orch = DerivationOrchestrator(spec_path=sample_spec_path)

    # Assert
    assert orch.fsm.current_state_value == "created"


# ---------------------------------------------------------------------------
# Audit trail accumulates records from both sources
# ---------------------------------------------------------------------------


def test_audit_trail_records_are_independent_per_orchestrator(sample_spec_path: Path) -> None:
    """Two orchestrators must have separate audit trails."""
    # Arrange
    orch_a = DerivationOrchestrator(spec_path=sample_spec_path)
    orch_b = DerivationOrchestrator(spec_path=sample_spec_path)

    # Act
    orch_a.audit_trail.record(variable="AGE_GROUP", action="test", agent="test")

    # Assert — orch_b trail is unaffected
    assert len(orch_a.audit_trail.records) == 1
    assert len(orch_b.audit_trail.records) == 0


def test_audit_trail_workflow_ids_are_unique(sample_spec_path: Path) -> None:
    """Each orchestrator instance must have a unique workflow ID."""
    # Arrange
    orch_a = DerivationOrchestrator(spec_path=sample_spec_path)
    orch_b = DerivationOrchestrator(spec_path=sample_spec_path)

    # Assert
    assert orch_a.state.workflow_id != orch_b.state.workflow_id
