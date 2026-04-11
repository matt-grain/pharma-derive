"""Tests for src/api/workflow_manager.py — lifecycle management of background workflows."""

from __future__ import annotations

import pytest

from src.api.workflow_manager import WorkflowManager


class _FakeStateRepo:
    """In-memory stub for WorkflowStateRepository — avoids DB in unit tests."""

    def __init__(self) -> None:
        self.store: dict[str, tuple[str, str]] = {}

    async def list_all(self) -> list[tuple[str, str, str]]:
        return [(wf_id, fsm, state) for wf_id, (fsm, state) in self.store.items()]

    async def delete(self, workflow_id: str) -> None:
        self.store.pop(workflow_id, None)


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


async def test_start_workflow_registers_interpreter(sample_spec_path: str) -> None:
    """Starting a workflow creates an interpreter and context accessible by ID."""
    # Arrange
    manager = WorkflowManager()

    # Act
    wf_id = await manager.start_workflow(sample_spec_path)

    # Assert
    assert manager.get_interpreter(wf_id) is not None
    assert manager.get_context(wf_id) is not None
    assert manager.get_fsm(wf_id) is not None
    assert manager.is_running(wf_id)
    assert wf_id in manager.list_workflow_ids()

    # Cleanup
    await manager.cancel_active()


async def test_is_known_after_start_returns_true(sample_spec_path: str) -> None:
    # Arrange
    manager = WorkflowManager()

    # Act
    wf_id = await manager.start_workflow(sample_spec_path)

    # Assert
    assert manager.is_known(wf_id) is True

    # Cleanup
    await manager.cancel_active()


async def test_delete_workflow_removes_from_history() -> None:
    # Arrange — seed history via load_history so the workflow is "known"
    manager = WorkflowManager()
    state_json = '{"study": "test", "derived_variables": [], "errors": [], "dag_nodes": {}}'
    fake_repo = _FakeStateRepo()
    fake_repo.store["wf-test-123"] = ("completed", state_json)
    await manager.load_history(fake_repo)  # type: ignore[arg-type]  # fake satisfies the protocol
    assert manager.is_known("wf-test-123")

    # Act
    await manager.delete_workflow("wf-test-123", fake_repo)  # type: ignore[arg-type]  # fake satisfies the protocol

    # Assert
    assert not manager.is_known("wf-test-123")


@pytest.fixture
def sample_spec_path() -> str:
    """Path to a valid spec for testing."""
    return "specs/simple_mock.yaml"
