"""Tests for src/engine/workflow_fsm.py — FSM states and transitions."""

from __future__ import annotations

import pytest
from statemachine.exceptions import TransitionNotAllowed

from src.engine.workflow_fsm import WorkflowFSM


@pytest.fixture
def fsm() -> WorkflowFSM:
    return WorkflowFSM(workflow_id="test-wf-001")


def test_fsm_initial_state_is_created(fsm: WorkflowFSM) -> None:
    assert fsm.current_state_value == "created"


def test_fsm_valid_transition_succeeds(fsm: WorkflowFSM) -> None:
    fsm.start_spec_review()

    assert fsm.current_state_value == "spec_review"


def test_fsm_full_happy_path(fsm: WorkflowFSM) -> None:
    fsm.start_spec_review()
    fsm.finish_spec_review()
    fsm.start_deriving()
    fsm.start_verifying()
    fsm.finish_review_from_verify()
    fsm.start_auditing()
    fsm.finish()

    assert fsm.current_state_value == "completed"


def test_fsm_invalid_transition_raises(fsm: WorkflowFSM) -> None:
    # start_deriving requires dag_built state, not created
    with pytest.raises(TransitionNotAllowed):
        fsm.start_deriving()


def test_fsm_fail_from_spec_review(fsm: WorkflowFSM) -> None:
    fsm.start_spec_review()
    fsm.fail()

    assert fsm.current_state_value == "failed"


def test_fsm_fail_from_deriving(fsm: WorkflowFSM) -> None:
    fsm.start_spec_review()
    fsm.finish_spec_review()
    fsm.start_deriving()
    fsm.fail()

    assert fsm.current_state_value == "failed"


def test_fsm_fail_from_verifying(fsm: WorkflowFSM) -> None:
    fsm.start_spec_review()
    fsm.finish_spec_review()
    fsm.start_deriving()
    fsm.start_verifying()
    fsm.fail()

    assert fsm.current_state_value == "failed"


def test_fsm_completed_is_final(fsm: WorkflowFSM) -> None:
    fsm.start_spec_review()
    fsm.finish_spec_review()
    fsm.start_deriving()
    fsm.start_verifying()
    fsm.finish_review_from_verify()
    fsm.start_auditing()
    fsm.finish()

    with pytest.raises(TransitionNotAllowed):
        fsm.start_spec_review()


def test_fsm_failed_is_final(fsm: WorkflowFSM) -> None:
    fsm.fail()

    with pytest.raises(TransitionNotAllowed):
        fsm.start_spec_review()


def test_fsm_after_transition_creates_audit_record(fsm: WorkflowFSM) -> None:
    assert len(fsm.audit_records) == 0

    fsm.start_spec_review()

    assert len(fsm.audit_records) == 1
    record = fsm.audit_records[0]
    assert record.action == "state_transition:spec_review"
    assert record.agent == "orchestrator"
    assert record.workflow_id == "test-wf-001"


def test_fsm_verify_to_debug_to_verify_loop(fsm: WorkflowFSM) -> None:
    fsm.start_spec_review()
    fsm.finish_spec_review()
    fsm.start_deriving()
    fsm.start_verifying()
    fsm.start_debugging()
    fsm.retry_from_debug()

    assert fsm.current_state_value == "verifying"


def test_fsm_verify_to_deriving_loop(fsm: WorkflowFSM) -> None:
    fsm.start_spec_review()
    fsm.finish_spec_review()
    fsm.start_deriving()
    fsm.start_verifying()
    fsm.next_variable()

    assert fsm.current_state_value == "deriving"
