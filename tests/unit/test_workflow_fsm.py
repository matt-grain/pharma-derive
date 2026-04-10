"""Tests for src/engine/workflow_fsm.py — FSM states and transitions."""

from __future__ import annotations

import pytest
from statemachine.exceptions import TransitionNotAllowed

from src.domain.workflow_fsm import WorkflowFSM


@pytest.fixture
def fsm() -> WorkflowFSM:
    return WorkflowFSM(workflow_id="test-wf-001")


def test_fsm_initial_state_is_created(fsm: WorkflowFSM) -> None:
    # Act & Assert
    assert fsm.current_state_value == "created"


def test_fsm_valid_transition_succeeds(fsm: WorkflowFSM) -> None:
    # Act
    fsm.start_spec_review()

    # Assert
    assert fsm.current_state_value == "spec_review"


def test_fsm_full_happy_path(fsm: WorkflowFSM) -> None:
    # Act
    fsm.start_spec_review()
    fsm.finish_spec_review()
    fsm.start_deriving()
    fsm.start_verifying()
    fsm.finish_review_from_verify()
    fsm.start_auditing()
    fsm.finish()

    # Assert
    assert fsm.current_state_value == "completed"


def test_fsm_invalid_transition_raises(fsm: WorkflowFSM) -> None:
    # Act & Assert — start_deriving requires dag_built state, not created
    with pytest.raises(TransitionNotAllowed):
        fsm.start_deriving()


def test_fsm_fail_from_spec_review(fsm: WorkflowFSM) -> None:
    # Arrange
    fsm.start_spec_review()

    # Act
    fsm.fail()

    # Assert
    assert fsm.current_state_value == "failed"


def test_fsm_fail_from_deriving(fsm: WorkflowFSM) -> None:
    # Arrange
    fsm.start_spec_review()
    fsm.finish_spec_review()
    fsm.start_deriving()

    # Act
    fsm.fail()

    # Assert
    assert fsm.current_state_value == "failed"


def test_fsm_fail_from_verifying(fsm: WorkflowFSM) -> None:
    # Arrange
    fsm.start_spec_review()
    fsm.finish_spec_review()
    fsm.start_deriving()
    fsm.start_verifying()

    # Act
    fsm.fail()

    # Assert
    assert fsm.current_state_value == "failed"


def test_fsm_completed_is_final(fsm: WorkflowFSM) -> None:
    # Arrange
    fsm.start_spec_review()
    fsm.finish_spec_review()
    fsm.start_deriving()
    fsm.start_verifying()
    fsm.finish_review_from_verify()
    fsm.start_auditing()
    fsm.finish()

    # Act & Assert
    with pytest.raises(TransitionNotAllowed):
        fsm.start_spec_review()


def test_fsm_failed_is_final(fsm: WorkflowFSM) -> None:
    # Arrange
    fsm.fail()

    # Act & Assert
    with pytest.raises(TransitionNotAllowed):
        fsm.start_spec_review()


def test_fsm_after_transition_creates_audit_record(fsm: WorkflowFSM) -> None:
    # Arrange
    assert len(fsm.audit_records) == 0

    # Act
    fsm.start_spec_review()

    # Assert
    assert len(fsm.audit_records) == 1
    record = fsm.audit_records[0]
    assert record.action == "state_transition:spec_review"
    assert record.agent == "orchestrator"
    assert record.workflow_id == "test-wf-001"


def test_fsm_verify_to_debug_to_verify_loop(fsm: WorkflowFSM) -> None:
    # Arrange
    fsm.start_spec_review()
    fsm.finish_spec_review()
    fsm.start_deriving()
    fsm.start_verifying()
    fsm.start_debugging()

    # Act
    fsm.retry_from_debug()

    # Assert
    assert fsm.current_state_value == "verifying"


def test_fsm_verify_to_deriving_loop(fsm: WorkflowFSM) -> None:
    # Arrange
    fsm.start_spec_review()
    fsm.finish_spec_review()
    fsm.start_deriving()
    fsm.start_verifying()

    # Act
    fsm.next_variable()

    # Assert
    assert fsm.current_state_value == "deriving"


def test_fsm_fail_from_dag_built_transitions_to_failed() -> None:
    """FSM can transition from dag_built to failed."""
    # Arrange
    fsm = WorkflowFSM(workflow_id="test-fail-dag")
    fsm.start_spec_review()
    fsm.finish_spec_review()

    # Act
    fsm.fail_from_dag_built()

    # Assert
    assert fsm.current_state_value == "failed"


def test_fsm_fail_from_debugging_transitions_to_failed() -> None:
    """FSM can transition from debugging to failed."""
    # Arrange
    fsm = WorkflowFSM(workflow_id="test-fail-debug")
    fsm.start_spec_review()
    fsm.finish_spec_review()
    fsm.start_deriving()
    fsm.start_verifying()
    fsm.start_debugging()

    # Act
    fsm.fail_from_debugging()

    # Assert
    assert fsm.current_state_value == "failed"


def test_fsm_fail_from_review_transitions_to_failed() -> None:
    """FSM can transition from review to failed."""
    # Arrange
    fsm = WorkflowFSM(workflow_id="test-fail-review")
    fsm.start_spec_review()
    fsm.finish_spec_review()
    fsm.start_deriving()
    fsm.start_verifying()
    fsm.finish_review_from_verify()

    # Act
    fsm.fail_from_review()

    # Assert
    assert fsm.current_state_value == "failed"


def test_fsm_fail_from_auditing_transitions_to_failed() -> None:
    """FSM can transition from auditing to failed."""
    # Arrange
    fsm = WorkflowFSM(workflow_id="test-fail-audit")
    fsm.start_spec_review()
    fsm.finish_spec_review()
    fsm.start_deriving()
    fsm.start_verifying()
    fsm.finish_review_from_verify()
    fsm.start_auditing()

    # Act
    fsm.fail_from_auditing()

    # Assert
    assert fsm.current_state_value == "failed"


def test_fsm_finish_review_from_debug_transitions_to_review() -> None:
    """FSM can transition from debugging to review."""
    # Arrange
    fsm = WorkflowFSM(workflow_id="test-debug-review")
    fsm.start_spec_review()
    fsm.finish_spec_review()
    fsm.start_deriving()
    fsm.start_verifying()
    fsm.start_debugging()

    # Act
    fsm.finish_review_from_debug()

    # Assert
    assert fsm.current_state_value == "review"


@pytest.mark.parametrize(
    ("start_state", "transitions"),
    [
        ("created", []),
        ("spec_review", ["start_spec_review"]),
        ("dag_built", ["start_spec_review", "finish_spec_review"]),
        ("deriving", ["start_spec_review", "finish_spec_review", "start_deriving"]),
        ("verifying", ["start_spec_review", "finish_spec_review", "start_deriving", "start_verifying"]),
    ],
)
def test_fsm_fail_method_from_non_terminal_state_transitions_to_failed(
    start_state: str,
    transitions: list[str],
) -> None:
    """The fail() helper method works from any non-terminal state."""
    # Arrange
    fsm = WorkflowFSM(workflow_id=f"test-fail-{start_state}")
    for t in transitions:
        getattr(fsm, t)()

    # Act
    fsm.fail("test error")

    # Assert
    assert fsm.current_state_value == "failed"
