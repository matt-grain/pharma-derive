"""Tests for src/api/workflow_manager.py — lifecycle management of background workflows."""

from __future__ import annotations

import pytest

from src.api.workflow_manager import WorkflowManager


async def test_workflow_manager_starts_empty() -> None:
    # Arrange
    manager = WorkflowManager()

    # Act & Assert
    assert manager.active_count == 0
    assert manager.list_workflow_ids() == []


async def test_get_orchestrator_unknown_id_returns_none() -> None:
    # Arrange
    manager = WorkflowManager()

    # Act
    result = manager.get_orchestrator("nonexistent")

    # Assert
    assert result is None


async def test_get_result_unknown_id_returns_none() -> None:
    # Arrange
    manager = WorkflowManager()

    # Act
    result = manager.get_result("nonexistent")

    # Assert
    assert result is None


async def test_is_running_unknown_id_returns_false() -> None:
    # Arrange
    manager = WorkflowManager()

    # Act & Assert
    assert manager.is_running("nonexistent") is False


async def test_start_workflow_registers_orchestrator(sample_spec_path: str) -> None:
    """Starting a workflow creates an orchestrator accessible by ID."""
    # Arrange
    manager = WorkflowManager()

    # Act
    wf_id = await manager.start_workflow(sample_spec_path)

    # Assert
    assert manager.get_orchestrator(wf_id) is not None
    assert manager.is_running(wf_id)
    assert wf_id in manager.list_workflow_ids()

    # Cleanup
    await manager.cancel_active()


@pytest.fixture
def sample_spec_path() -> str:
    """Path to a valid spec for testing."""
    return "specs/simple_mock.yaml"
