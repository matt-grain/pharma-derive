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
