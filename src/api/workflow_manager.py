"""Workflow lifecycle manager — starts background tasks, tracks runs."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from src.config.settings import get_settings
from src.domain.workflow_models import (
    WorkflowResult,  # noqa: TC001 — used in asyncio.Task[WorkflowResult] dict type, not just annotations
)
from src.factory import create_orchestrator

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.engine.orchestrator import DerivationOrchestrator
    from src.persistence.workflow_state_repo import WorkflowStateRepository


class _HistoricState:
    """Lightweight stand-in for a DerivationOrchestrator loaded from DB history."""

    def __init__(self, workflow_id: str, fsm_state: str, state_json: str) -> None:
        data = json.loads(state_json)
        self.workflow_id = workflow_id
        self.fsm_state = fsm_state
        self.study: str | None = data.get("study")
        self.derived_variables: list[str] = data.get("derived_variables", [])
        self.errors: list[str] = data.get("errors", [])
        self.dag_nodes: dict[str, dict[str, object]] = data.get("dag_nodes", {})


class WorkflowManager:
    """Manages active workflow runs as background asyncio tasks."""

    def __init__(self) -> None:
        self._active: dict[str, asyncio.Task[WorkflowResult]] = {}
        self._orchestrators: dict[str, DerivationOrchestrator] = {}
        self._sessions: dict[str, AsyncSession] = {}
        self._results: dict[str, WorkflowResult] = {}
        self._history: dict[str, _HistoricState] = {}

    async def load_history(self, state_repo: WorkflowStateRepository) -> None:
        """Load completed/failed workflows from DB so they appear in listings after restart."""
        rows = await state_repo.list_all()
        for wf_id, fsm_state, state_json in rows:
            self._history[wf_id] = _HistoricState(wf_id, fsm_state, state_json)
        logger.info("Loaded {n} historic workflows from DB", n=len(self._history))

    async def start_workflow(
        self,
        spec_path: str,
        llm_base_url: str | None = None,
        output_dir: Path | None = None,
    ) -> str:
        """Create orchestrator, start run as background task, return workflow_id."""
        effective_output = output_dir or Path(get_settings().output_dir)
        orch, session = await create_orchestrator(spec_path, llm_base_url, effective_output)
        wf_id = orch.state.workflow_id
        self._orchestrators[wf_id] = orch
        self._sessions[wf_id] = session
        task = asyncio.create_task(self._run_and_cleanup(wf_id, orch, session))
        self._active[wf_id] = task
        return wf_id

    async def _run_and_cleanup(
        self,
        wf_id: str,
        orch: DerivationOrchestrator,
        session: AsyncSession,
    ) -> WorkflowResult:
        """Run orchestrator, commit session, store result."""
        try:
            result = await orch.run()
            await session.commit()
            self._results[wf_id] = result
            return result
        except Exception:
            logger.exception("Workflow {wf_id} background task failed", wf_id=wf_id)
            await session.rollback()
            raise
        finally:
            await session.close()
            self._active.pop(wf_id, None)
            self._sessions.pop(wf_id, None)

    def get_orchestrator(self, workflow_id: str) -> DerivationOrchestrator | None:
        """Get orchestrator for a workflow (active or in-memory completed)."""
        return self._orchestrators.get(workflow_id)

    def get_historic(self, workflow_id: str) -> _HistoricState | None:
        """Get lightweight historic state loaded from DB."""
        return self._history.get(workflow_id)

    def get_result(self, workflow_id: str) -> WorkflowResult | None:
        """Get result for a completed workflow."""
        return self._results.get(workflow_id)

    def is_running(self, workflow_id: str) -> bool:
        """Check if a workflow is still running."""
        return workflow_id in self._active

    def is_known(self, workflow_id: str) -> bool:
        """Check if workflow exists in any state (active, completed, or historic)."""
        return workflow_id in self._orchestrators or workflow_id in self._history

    @property
    def active_count(self) -> int:
        """Number of currently running workflows."""
        return len(self._active)

    def list_workflow_ids(self) -> list[str]:
        """All known workflow IDs (active + completed + historic)."""
        return list({*self._active.keys(), *self._results.keys(), *self._history.keys()})

    async def delete_workflow(self, workflow_id: str, state_repo: WorkflowStateRepository) -> None:
        """Remove a workflow from all in-memory stores and delete its DB state."""
        self._orchestrators.pop(workflow_id, None)
        self._results.pop(workflow_id, None)
        self._history.pop(workflow_id, None)
        await state_repo.delete(workflow_id)

    async def cancel_active(self) -> None:
        """Cancel all running workflows. Used for graceful shutdown and test cleanup."""
        tasks = list(self._active.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
