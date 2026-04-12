"""Unit tests for PipelineContext — the shared mutable state container."""

from __future__ import annotations

import pytest

from src.audit.trail import AuditTrail
from src.engine.pipeline_context import PipelineContext


def _make_ctx(workflow_id: str = "wf-test") -> PipelineContext:
    """Return a minimal PipelineContext suitable for unit tests."""
    return PipelineContext(
        workflow_id=workflow_id,
        audit_trail=AuditTrail(workflow_id),
        llm_base_url="http://localhost:4010",
    )


# ---------------------------------------------------------------------------
# set_output / get_output
# ---------------------------------------------------------------------------


def test_set_output_and_get_output_roundtrip() -> None:
    # Arrange
    ctx = _make_ctx()

    # Act
    ctx.set_output("step_a", "result", 42)
    value = ctx.get_output("step_a", "result")

    # Assert
    assert value == 42


def test_set_output_multiple_keys_same_step() -> None:
    """Multiple keys under the same step ID are stored independently."""
    # Arrange
    ctx = _make_ctx()

    # Act
    ctx.set_output("step_a", "key1", "hello")
    ctx.set_output("step_a", "key2", [1, 2, 3])

    # Assert
    assert ctx.get_output("step_a", "key1") == "hello"
    assert ctx.get_output("step_a", "key2") == [1, 2, 3]


def test_set_output_overwrites_existing_key() -> None:
    """Setting the same key twice replaces the previous value."""
    # Arrange
    ctx = _make_ctx()
    ctx.set_output("step_a", "x", "original")

    # Act
    ctx.set_output("step_a", "x", "updated")

    # Assert
    assert ctx.get_output("step_a", "x") == "updated"


def test_get_output_missing_step_raises_key_error() -> None:
    # Arrange
    ctx = _make_ctx()

    # Act & Assert
    with pytest.raises(KeyError, match="step 'nonexistent'"):
        ctx.get_output("nonexistent", "key")


def test_get_output_missing_key_raises_key_error() -> None:
    # Arrange
    ctx = _make_ctx()
    ctx.set_output("step_a", "present_key", "value")

    # Act & Assert
    with pytest.raises(KeyError, match="missing_key"):
        ctx.get_output("step_a", "missing_key")


def test_get_output_missing_key_lists_available_keys_in_message() -> None:
    """Error message for a missing key includes the keys that ARE present."""
    # Arrange
    ctx = _make_ctx()
    ctx.set_output("step_a", "found_key", "v")

    # Act & Assert
    with pytest.raises(KeyError, match="found_key"):
        ctx.get_output("step_a", "absent_key")


# ---------------------------------------------------------------------------
# workflow_id propagation
# ---------------------------------------------------------------------------


def test_workflow_id_is_preserved() -> None:
    # Arrange & Act
    ctx = _make_ctx(workflow_id="my-run-42")

    # Assert
    assert ctx.workflow_id == "my-run-42"


# ---------------------------------------------------------------------------
# Default field values
# ---------------------------------------------------------------------------


def test_new_context_has_empty_step_outputs() -> None:
    # Arrange & Act
    ctx = _make_ctx()

    # Assert
    assert ctx.step_outputs == {}


def test_new_context_has_empty_errors_list() -> None:
    # Arrange & Act
    ctx = _make_ctx()

    # Assert
    assert ctx.errors == []


def test_errors_list_is_not_shared_across_instances() -> None:
    """Two independent contexts must not share the same errors list."""
    # Arrange
    ctx_a = _make_ctx("wf-a")
    ctx_b = _make_ctx("wf-b")

    # Act
    ctx_a.errors.append("something went wrong")

    # Assert
    assert ctx_b.errors == []


def test_step_outputs_dict_is_not_shared_across_instances() -> None:
    """Two independent contexts must not share the same step_outputs dict."""
    # Arrange
    ctx_a = _make_ctx("wf-a")
    ctx_b = _make_ctx("wf-b")

    # Act
    ctx_a.set_output("step_x", "val", 99)

    # Assert
    assert "step_x" not in ctx_b.step_outputs
