"""Tests for src/api/workflow_manager.py — lifecycle management of background workflows."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from src.api.workflow_manager import WorkflowManager
from src.audit.trail import AuditTrail
from src.engine.pipeline_context import PipelineContext


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

    # Act — patch persistence boundary so delete_workflow doesn't hit a real DB.
    # init_db is imported lazily inside delete_workflow, so we patch it at its definition site.
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session_factory = MagicMock(return_value=mock_session)
    with (
        patch("src.persistence.database.init_db", new_callable=AsyncMock, return_value=mock_session_factory),
        patch("src.persistence.workflow_state_repo.WorkflowStateRepository", return_value=AsyncMock()),
    ):
        await manager.delete_workflow("wf-test-123")

    # Assert
    assert not manager.is_known("wf-test-123")


async def test_start_workflow_populates_started_at(sample_spec_path: str) -> None:
    """After start_workflow, get_started_at returns an ISO 8601 timestamp."""
    # Arrange
    manager = WorkflowManager()

    # Act
    wf_id = await manager.start_workflow(sample_spec_path)

    # Assert
    started_at = manager.get_started_at(wf_id)
    assert started_at is not None
    # Sanity-check: looks like an ISO 8601 datetime (contains 'T' separator)
    assert "T" in started_at

    # Cleanup
    await manager.cancel_active()


async def test_run_and_cleanup_populates_completed_at_on_success() -> None:
    """After the pipeline task completes successfully, get_completed_at is set."""
    # Arrange
    manager = WorkflowManager()

    wf_id = "wf-test-success"
    ctx = PipelineContext(workflow_id=wf_id, audit_trail=AuditTrail(wf_id), llm_base_url="http://localhost")
    mock_interpreter = AsyncMock()
    mock_interpreter.run = AsyncMock(return_value=None)

    mock_fsm = MagicMock()
    mock_fsm.current_state_value = "completed"
    mock_fsm.is_terminal = True
    mock_fsm.is_failed = False

    mock_session = AsyncMock()

    manager._interpreters[wf_id] = mock_interpreter  # type: ignore[assignment]
    manager._contexts[wf_id] = ctx  # pyright: ignore[reportPrivateUsage]
    manager._fsms[wf_id] = mock_fsm  # pyright: ignore[reportPrivateUsage]
    manager._sessions[wf_id] = mock_session  # pyright: ignore[reportPrivateUsage]
    manager._started_at[wf_id] = "2024-01-01T00:00:00+00:00"  # pyright: ignore[reportPrivateUsage]

    with (
        patch("src.persistence.workflow_state_repo.WorkflowStateRepository") as mock_repo_cls,
        patch("src.api.workflow_lifecycle.serialize_ctx", return_value="{}"),
        patch("src.api.workflow_manager.build_result", return_value=MagicMock()),
        patch("src.api.workflow_manager.persist_audit_trail"),
    ):
        mock_repo_cls.return_value = AsyncMock()

        # Act
        await manager._run_and_cleanup(wf_id, mock_interpreter, ctx, mock_fsm, mock_session)  # pyright: ignore[reportPrivateUsage]

    # Assert
    completed_at = manager.get_completed_at(wf_id)
    assert completed_at is not None
    assert "T" in completed_at


async def test_run_and_cleanup_populates_completed_at_on_failure() -> None:
    """Even when the pipeline raises, the finally block sets completed_at."""
    # Arrange
    manager = WorkflowManager()

    wf_id = "wf-test-failure"
    ctx = PipelineContext(workflow_id=wf_id, audit_trail=AuditTrail(wf_id), llm_base_url="http://localhost")
    mock_interpreter = AsyncMock()
    mock_interpreter.run = AsyncMock(side_effect=RuntimeError("pipeline boom"))

    mock_fsm = MagicMock()
    mock_fsm.current_state_value = "failed"

    mock_session = AsyncMock()

    manager._interpreters[wf_id] = mock_interpreter  # type: ignore[assignment]
    manager._contexts[wf_id] = ctx  # pyright: ignore[reportPrivateUsage]
    manager._fsms[wf_id] = mock_fsm  # pyright: ignore[reportPrivateUsage]
    manager._sessions[wf_id] = mock_session  # pyright: ignore[reportPrivateUsage]
    manager._started_at[wf_id] = "2024-01-01T00:00:00+00:00"  # pyright: ignore[reportPrivateUsage]

    with (
        patch("src.api.workflow_manager.persist_error_state", new_callable=AsyncMock),
        patch("src.api.workflow_manager.persist_audit_trail"),
        pytest.raises(RuntimeError, match="pipeline boom"),
    ):
        # Act — exception must propagate
        await manager._run_and_cleanup(wf_id, mock_interpreter, ctx, mock_fsm, mock_session)  # pyright: ignore[reportPrivateUsage]

    # Assert — completed_at set by finally block despite the exception
    completed_at = manager.get_completed_at(wf_id)
    assert completed_at is not None
    assert "T" in completed_at


async def test_get_started_at_unknown_workflow_returns_none() -> None:
    """get_started_at returns None for an unknown workflow ID."""
    # Arrange
    manager = WorkflowManager()

    # Act & Assert
    assert manager.get_started_at("nonexistent") is None


async def test_get_completed_at_unknown_workflow_returns_none() -> None:
    """get_completed_at returns None for an unknown or still-running workflow ID."""
    # Arrange
    manager = WorkflowManager()

    # Act & Assert
    assert manager.get_completed_at("nonexistent") is None


async def test_run_and_cleanup_writes_audit_trail_file_on_success(tmp_path: Path) -> None:
    """On successful completion, persist_audit_trail writes a JSON file to output_dir."""
    import json as json_module

    from src.api.workflow_lifecycle import persist_audit_trail

    # Arrange
    wf_id = "wf-audit-success"
    trail = AuditTrail(wf_id)
    trail.record(variable="AAGE", action="derivation_complete", agent="coder", details={"status": "approved"})
    ctx = PipelineContext(workflow_id=wf_id, audit_trail=trail, llm_base_url="http://localhost")

    # Act
    persist_audit_trail(ctx, tmp_path)

    # Assert
    audit_path = tmp_path / f"{wf_id}_audit.json"
    assert audit_path.exists(), "Audit JSON file must be written on workflow completion"
    records = json_module.loads(audit_path.read_text(encoding="utf-8"))
    assert len(records) == 1
    assert records[0]["variable"] == "AAGE"
    assert records[0]["action"] == "derivation_complete"


async def test_run_and_cleanup_writes_audit_trail_file_on_failure(tmp_path: Path) -> None:
    """When the pipeline raises, the finally block still writes the audit trail file."""
    # Arrange
    manager = WorkflowManager()
    wf_id = "wf-audit-failure"
    trail = AuditTrail(wf_id)
    trail.record(variable="AAGE", action="derivation_start", agent="coder")
    ctx = PipelineContext(workflow_id=wf_id, audit_trail=trail, llm_base_url="http://localhost")

    mock_interpreter = AsyncMock()
    mock_interpreter.run = AsyncMock(side_effect=RuntimeError("pipeline boom"))
    mock_fsm = MagicMock()
    mock_fsm.current_state_value = "failed"
    mock_session = AsyncMock()

    manager._interpreters[wf_id] = mock_interpreter  # type: ignore[assignment]
    manager._contexts[wf_id] = ctx  # pyright: ignore[reportPrivateUsage]
    manager._fsms[wf_id] = mock_fsm  # pyright: ignore[reportPrivateUsage]
    manager._sessions[wf_id] = mock_session  # pyright: ignore[reportPrivateUsage]
    manager._started_at[wf_id] = "2024-01-01T00:00:00+00:00"  # pyright: ignore[reportPrivateUsage]

    with (
        patch("src.api.workflow_manager.persist_error_state", new_callable=AsyncMock),
        patch("src.api.workflow_manager.get_settings", return_value=MagicMock(output_dir=str(tmp_path))),
        pytest.raises(RuntimeError, match="pipeline boom"),
    ):
        # Act — exception must propagate
        await manager._run_and_cleanup(wf_id, mock_interpreter, ctx, mock_fsm, mock_session)  # pyright: ignore[reportPrivateUsage]

    # Assert — audit file written by the finally block despite the exception.
    # The file contains both the original derivation_start record and the
    # workflow_failed record appended by the except branch.
    import json as json_module

    audit_path = tmp_path / f"{wf_id}_audit.json"
    assert audit_path.exists(), "Audit JSON file must be written even when pipeline fails"
    records = json_module.loads(audit_path.read_text(encoding="utf-8"))
    assert len(records) == 2
    assert records[0]["variable"] == "AAGE"
    assert records[0]["action"] == "derivation_start"
    assert records[1]["action"] == "workflow_failed"
    assert records[1]["details"]["error"] == "pipeline boom"


async def test_rerun_workflow_starts_new_run_and_deletes_old() -> None:
    """rerun_workflow starts a fresh run with the same spec then deletes the old one."""
    from pathlib import Path as _Path

    # Arrange
    manager = WorkflowManager()
    old_id = "wf-old"
    old_ctx = PipelineContext(workflow_id=old_id, audit_trail=AuditTrail(old_id), llm_base_url="")
    old_ctx.step_outputs["_init"] = {"spec_path": _Path("specs/simple_mock.yaml")}
    manager._contexts[old_id] = old_ctx  # pyright: ignore[reportPrivateUsage]

    async def fake_start_workflow(spec_path: str, llm_base_url: str | None = None) -> str:
        # Compare as pathlib paths so the test works on Windows (backslash) and POSIX (slash)
        assert _Path(spec_path) == _Path("specs/simple_mock.yaml")
        assert llm_base_url is None
        return "wf-new"

    deleted: list[str] = []

    async def fake_delete_workflow(wf_id: str) -> None:
        deleted.append(wf_id)

    manager.start_workflow = fake_start_workflow  # type: ignore[method-assign]
    manager.delete_workflow = fake_delete_workflow  # type: ignore[method-assign]

    # Act
    new_id = await manager.rerun_workflow(old_id)

    # Assert
    assert new_id == "wf-new"
    assert deleted == [old_id]


async def test_rerun_workflow_preserves_old_when_start_fails() -> None:
    """If start_workflow raises, the old workflow is NOT deleted — restart is atomic."""
    from pathlib import Path as _Path

    # Arrange
    manager = WorkflowManager()
    old_id = "wf-old-preserved"
    old_ctx = PipelineContext(workflow_id=old_id, audit_trail=AuditTrail(old_id), llm_base_url="")
    old_ctx.step_outputs["_init"] = {"spec_path": _Path("specs/simple_mock.yaml")}
    manager._contexts[old_id] = old_ctx  # pyright: ignore[reportPrivateUsage]

    async def failing_start(spec_path: str, llm_base_url: str | None = None) -> str:
        _ = spec_path, llm_base_url
        msg = "boom"
        raise RuntimeError(msg)

    deleted: list[str] = []

    async def fake_delete_workflow(wf_id: str) -> None:
        deleted.append(wf_id)

    manager.start_workflow = failing_start  # type: ignore[method-assign]
    manager.delete_workflow = fake_delete_workflow  # type: ignore[method-assign]

    # Act & Assert
    with pytest.raises(RuntimeError, match="boom"):
        await manager.rerun_workflow(old_id)
    assert deleted == []  # old workflow must survive when new one fails to start


async def test_rerun_workflow_missing_everywhere_raises_keyerror() -> None:
    """rerun_workflow raises KeyError when neither in-memory ctx nor history can provide a spec."""
    # Arrange
    manager = WorkflowManager()

    # Act & Assert
    with pytest.raises(KeyError, match="no recoverable spec_path"):
        await manager.rerun_workflow("nonexistent")


async def test_rerun_workflow_falls_back_to_historic_spec_path() -> None:
    """When ctx is gone but history carries spec_path, rerun uses it."""
    import json as _json

    from src.api.workflow_serializer import HistoricState

    # Arrange
    manager = WorkflowManager()
    old_id = "wf-historic"
    state_json = _json.dumps({"spec_path": "specs/simple_mock.yaml", "errors": [], "dag_nodes": {}})
    manager._history[old_id] = HistoricState(old_id, "completed", state_json)  # pyright: ignore[reportPrivateUsage]

    captured: dict[str, str] = {}

    async def fake_start(spec_path: str, llm_base_url: str | None = None) -> str:
        captured["spec"] = spec_path
        return "wf-new-from-historic"

    manager.start_workflow = fake_start  # type: ignore[method-assign]

    # Act
    new_id = await manager.rerun_workflow(old_id)

    # Assert
    assert new_id == "wf-new-from-historic"
    assert captured["spec"] == "specs/simple_mock.yaml"


async def test_run_and_cleanup_records_workflow_failed_audit_on_exception() -> None:
    """When the interpreter raises, an audit record with the error is appended before re-raise."""
    from src.domain.enums import AuditAction

    # Arrange
    manager = WorkflowManager()
    wf_id = "wf-test-failure-audit"
    ctx = PipelineContext(workflow_id=wf_id, audit_trail=AuditTrail(wf_id), llm_base_url="http://localhost")
    mock_interpreter = AsyncMock()
    mock_interpreter.run = AsyncMock(side_effect=RuntimeError("kaboom"))
    mock_interpreter.current_step = "derive_variables"

    mock_fsm = MagicMock()
    mock_fsm.current_state_value = "failed"
    mock_session = AsyncMock()

    manager._interpreters[wf_id] = mock_interpreter  # type: ignore[assignment]  # pyright: ignore[reportPrivateUsage]
    manager._contexts[wf_id] = ctx  # pyright: ignore[reportPrivateUsage]
    manager._fsms[wf_id] = mock_fsm  # pyright: ignore[reportPrivateUsage]
    manager._sessions[wf_id] = mock_session  # pyright: ignore[reportPrivateUsage]
    manager._started_at[wf_id] = "2024-01-01T00:00:00+00:00"  # pyright: ignore[reportPrivateUsage]

    with (
        patch("src.api.workflow_manager.persist_error_state", new_callable=AsyncMock),
        patch("src.api.workflow_manager.persist_audit_trail"),
        pytest.raises(RuntimeError, match="kaboom"),
    ):
        # Act
        await manager._run_and_cleanup(wf_id, mock_interpreter, ctx, mock_fsm, mock_session)  # pyright: ignore[reportPrivateUsage]

    # Assert — audit trail contains a workflow_failed record with the error
    failed_records = [r for r in ctx.audit_trail.records if r.action == AuditAction.WORKFLOW_FAILED]
    assert len(failed_records) == 1
    details = failed_records[0].details
    assert details["error"] == "kaboom"
    assert details["error_type"] == "RuntimeError"
    assert details["failed_step"] == "derive_variables"


async def test_list_workflow_ids_includes_failed_workflows() -> None:
    """Failed workflows must stay visible in list_workflow_ids after _active is cleared.

    Regression: previously used _active.keys() which is emptied in the finally block
    of _run_and_cleanup, so failed workflows vanished from listings even though their
    ctx/fsm remained in memory. list_workflow_ids must mirror is_known and check
    _interpreters instead.
    """
    # Arrange
    manager = WorkflowManager()
    wf_id = "wf-failed"
    manager._interpreters[wf_id] = MagicMock()  # type: ignore[assignment]  # pyright: ignore[reportPrivateUsage]

    # Act
    ids = manager.list_workflow_ids()

    # Assert
    assert wf_id in ids
    assert manager.is_known(wf_id)


async def test_run_and_cleanup_checkpoints_after_each_step() -> None:
    """Interpreter receives an on_step_complete callback that drives state_repo.save + commit."""
    # Arrange
    manager = WorkflowManager()
    wf_id = "wf-test-checkpoint"
    ctx = PipelineContext(workflow_id=wf_id, audit_trail=AuditTrail(wf_id), llm_base_url="http://localhost")

    captured: dict[str, object] = {}

    async def fake_run(on_step_complete: object = None) -> None:
        # Simulate the interpreter calling the checkpoint after each step
        captured["callback"] = on_step_complete
        assert on_step_complete is not None, "workflow_manager must pass a checkpoint callback"
        await on_step_complete("parse_spec")  # type: ignore[operator]
        await on_step_complete("build_dag")  # type: ignore[operator]

    mock_interpreter = AsyncMock()
    mock_interpreter.run = fake_run

    mock_fsm = MagicMock()
    mock_fsm.current_state_value = "build_dag"
    mock_fsm.is_terminal = True
    mock_fsm.is_failed = False

    mock_session = AsyncMock()

    manager._interpreters[wf_id] = mock_interpreter  # type: ignore[assignment]
    manager._contexts[wf_id] = ctx  # pyright: ignore[reportPrivateUsage]
    manager._fsms[wf_id] = mock_fsm  # pyright: ignore[reportPrivateUsage]
    manager._sessions[wf_id] = mock_session  # pyright: ignore[reportPrivateUsage]
    manager._started_at[wf_id] = "2024-01-01T00:00:00+00:00"  # pyright: ignore[reportPrivateUsage]

    fake_repo = AsyncMock()

    with (
        patch("src.persistence.workflow_state_repo.WorkflowStateRepository", return_value=fake_repo),
        patch("src.api.workflow_lifecycle.serialize_ctx", return_value="{}"),
        patch("src.api.workflow_manager.build_result", return_value=MagicMock()),
        patch("src.api.workflow_manager.persist_audit_trail"),
    ):
        # Act
        await manager._run_and_cleanup(wf_id, mock_interpreter, ctx, mock_fsm, mock_session)  # pyright: ignore[reportPrivateUsage]

    # Assert — two checkpoints + one final save = 3 state_repo.save calls
    assert fake_repo.save.await_count == 3
    # Two checkpoint commits + one final commit
    assert mock_session.commit.await_count == 3


@pytest.fixture
def sample_spec_path() -> str:
    """Path to a valid spec for testing."""
    return "specs/simple_mock.yaml"
