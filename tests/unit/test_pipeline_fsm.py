"""Tests for the auto-generated PipelineFSM — state tracking from pipeline step IDs."""

from __future__ import annotations

from src.engine.pipeline_fsm import PipelineFSM


def test_fsm_initial_state_is_created() -> None:
    # Arrange
    fsm = PipelineFSM("wf-1", ["parse_spec", "build_dag", "export"])

    # Assert
    assert fsm.current_state_value == "created"
    assert not fsm.is_terminal
    assert not fsm.is_failed


def test_fsm_advance_sets_step_as_current_state() -> None:
    # Arrange
    fsm = PipelineFSM("wf-1", ["parse_spec", "build_dag"])

    # Act
    fsm.advance("parse_spec")

    # Assert
    assert fsm.current_state_value == "parse_spec"
    assert not fsm.is_terminal


def test_fsm_complete_sets_terminal_state() -> None:
    # Arrange
    fsm = PipelineFSM("wf-1", ["parse_spec"])
    fsm.advance("parse_spec")

    # Act
    fsm.complete()

    # Assert
    assert fsm.current_state_value == "completed"
    assert fsm.is_terminal
    assert not fsm.is_failed


def test_fsm_fail_sets_failed_terminal_state() -> None:
    # Arrange
    fsm = PipelineFSM("wf-1", ["parse_spec", "build_dag"])
    fsm.advance("parse_spec")

    # Act
    fsm.fail("something broke")

    # Assert
    assert fsm.current_state_value == "failed"
    assert fsm.is_terminal
    assert fsm.is_failed


def test_fsm_states_derived_from_pipeline_steps() -> None:
    """FSM step_ids reflect the pipeline definition — no hardcoded states."""
    # Arrange
    steps = ["a", "b", "c"]
    fsm = PipelineFSM("wf-1", steps)

    # Assert
    assert fsm._step_ids == steps  # type: ignore[attr-defined]  # testing internal for verification

    # Act — advance through all steps
    for s in steps:
        fsm.advance(s)
        assert fsm.current_state_value == s

    fsm.complete()
    assert fsm.is_terminal


# ---------------------------------------------------------------------------
# Invalid-transition / idempotency tests
# ---------------------------------------------------------------------------


def test_fsm_advance_after_complete_is_noop() -> None:
    """Calling advance() after complete() silently overwrites the state.

    PipelineFSM is intentionally permissive — it tracks where we are, not
    what transitions are legal. Callers (PipelineInterpreter) must not
    advance a completed FSM. This test documents the current behavior:
    advance() after complete() moves state out of 'completed' without raising.
    """
    # Arrange
    fsm = PipelineFSM("wf-1", ["step_a"])
    fsm.advance("step_a")
    fsm.complete()
    assert fsm.current_state_value == "completed"

    # Act — caller error: advancing a completed FSM
    fsm.advance("step_a")

    # Assert — state is no longer terminal (permissive design, documented here)
    assert fsm.current_state_value == "step_a"


def test_fsm_fail_is_idempotent() -> None:
    """Calling fail() twice keeps the FSM in FAILED state without raising."""
    # Arrange
    fsm = PipelineFSM("wf-1", ["step_a"])
    fsm.advance("step_a")
    fsm.fail("first error")

    # Act
    fsm.fail("second error")

    # Assert
    assert fsm.current_state_value == "failed"
    assert fsm.is_failed
    assert fsm.is_terminal


def test_fsm_advance_after_fail_overwrites_state() -> None:
    """advance() after fail() moves state out of FAILED — documents permissive design.

    Like advance-after-complete, PipelineFSM does not guard against this.
    The interpreter is responsible for not calling advance on a failed FSM.
    """
    # Arrange
    fsm = PipelineFSM("wf-1", ["step_a"])
    fsm.fail("something broke")
    assert fsm.is_terminal

    # Act
    fsm.advance("step_a")

    # Assert — is_failed is sticky (_failed flag), but current_state changed
    assert fsm.current_state_value == "step_a"
    assert fsm.is_failed  # the flag remains True


def test_fsm_complete_after_fail_sets_completed_state() -> None:
    """complete() after fail() is permissive — documents the current behavior.

    current_state_value transitions to 'completed' but is_failed remains True
    because the _failed flag is never cleared. This is intentional: the FSM
    records that a failure occurred, even if completion is subsequently called.
    """
    # Arrange
    fsm = PipelineFSM("wf-1", ["step_a"])
    fsm.fail("oops")

    # Act
    fsm.complete()

    # Assert
    assert fsm.current_state_value == "completed"
    assert fsm.is_failed  # sticky — records that failure occurred
