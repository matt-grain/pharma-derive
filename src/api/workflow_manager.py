"""Workflow lifecycle manager — starts background tasks, tracks runs."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from src.config.settings import get_settings
from src.domain.workflow_models import (
    WorkflowResult,
    WorkflowStatus,
)
from src.factory import create_pipeline_orchestrator

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.engine.orchestrator import DerivationOrchestrator
    from src.engine.pipeline_context import PipelineContext
    from src.engine.pipeline_fsm import PipelineFSM
    from src.engine.pipeline_interpreter import PipelineInterpreter
    from src.persistence.workflow_state_repo import WorkflowStateRepository


class _HistoricState:
    """Lightweight stand-in for a workflow loaded from DB history."""

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
        self._interpreters: dict[str, PipelineInterpreter] = {}
        self._contexts: dict[str, PipelineContext] = {}
        self._fsms: dict[str, PipelineFSM] = {}
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
        """Create pipeline interpreter, start run as background task, return workflow_id."""
        effective_output = output_dir or Path(get_settings().output_dir)
        interpreter, ctx, fsm, session = await create_pipeline_orchestrator(
            spec_path, llm_base_url=llm_base_url, output_dir=effective_output
        )
        wf_id = ctx.workflow_id
        self._interpreters[wf_id] = interpreter
        self._contexts[wf_id] = ctx
        self._fsms[wf_id] = fsm
        self._sessions[wf_id] = session
        task = asyncio.create_task(self._run_and_cleanup(wf_id, interpreter, ctx, fsm, session))
        self._active[wf_id] = task
        return wf_id

    async def _run_and_cleanup(
        self,
        wf_id: str,
        interpreter: PipelineInterpreter,
        ctx: PipelineContext,
        fsm: PipelineFSM,
        session: AsyncSession,
    ) -> WorkflowResult:
        """Run the pipeline interpreter, persist state, store result."""
        from src.persistence.workflow_state_repo import WorkflowStateRepository

        try:
            await interpreter.run()
            fsm.complete()
            state_repo = WorkflowStateRepository(session)
            await state_repo.save(
                workflow_id=wf_id,
                state_json=self._serialize_ctx(ctx, fsm.current_state_value),
                fsm_state=fsm.current_state_value,
            )
            await session.commit()
            result = self._build_result(wf_id, ctx, fsm)
            self._results[wf_id] = result
            logger.info("Workflow {wf_id} completed successfully", wf_id=wf_id)
            return result
        except Exception as exc:
            logger.exception("Workflow {wf_id} failed", wf_id=wf_id)
            fsm.fail(str(exc))
            await self._persist_error_state(wf_id, ctx, session)
            raise
        finally:
            await session.close()
            self._active.pop(wf_id, None)
            self._sessions.pop(wf_id, None)

    async def _persist_error_state(self, wf_id: str, ctx: PipelineContext, session: AsyncSession) -> None:
        """Best-effort persist of failed workflow state — rolls back on failure."""
        from src.persistence.workflow_state_repo import WorkflowStateRepository

        try:
            state_repo = WorkflowStateRepository(session)
            await state_repo.save(workflow_id=wf_id, state_json=self._serialize_ctx(ctx, "failed"), fsm_state="failed")
            await session.commit()
        except Exception:
            logger.exception("Failed to persist error state for {wf_id}", wf_id=wf_id)
            await session.rollback()

    @staticmethod
    def _serialize_ctx(ctx: PipelineContext, fsm_state: str) -> str:
        """Serialize pipeline context to JSON for DB persistence."""
        dag = ctx.dag
        dag_nodes: dict[str, dict[str, object]] = {}
        if dag is not None:
            for var in dag.execution_order:
                node = dag.get_node(var)
                dag_nodes[var] = {
                    "status": node.status.value,
                    "layer": node.layer,
                    "coder_code": node.coder_code,
                    "qc_code": node.qc_code,
                    "qc_verdict": node.qc_verdict.value if node.qc_verdict else None,
                    "approved_code": node.approved_code,
                    "dependencies": dag.get_dependencies(var),
                }
        return json.dumps(
            {
                "workflow_id": ctx.workflow_id,
                "status": fsm_state,
                "study": ctx.spec.metadata.study if ctx.spec else None,
                "derived_variables": list(dag.nodes if dag else {}),
                "errors": ctx.errors,
                "dag_nodes": dag_nodes,
            }
        )

    @staticmethod
    def _build_result(wf_id: str, ctx: PipelineContext, fsm: PipelineFSM) -> WorkflowResult:
        """Build immutable WorkflowResult from pipeline context and FSM state."""
        from src.domain.models import DerivationStatus

        dag = ctx.dag
        qc_summary = (
            {v: (n.qc_verdict.value if n.qc_verdict else DerivationStatus.PENDING.value) for v, n in dag.nodes.items()}
            if dag
            else {}
        )
        derived = [v for v, n in dag.nodes.items() if n.status == DerivationStatus.APPROVED] if dag else []
        is_done = fsm.is_terminal and not fsm.is_failed
        return WorkflowResult(
            workflow_id=wf_id,
            study=ctx.spec.metadata.study if ctx.spec else "unknown",
            status=WorkflowStatus.COMPLETED if is_done else WorkflowStatus.FAILED,
            derived_variables=derived,
            qc_summary=qc_summary,
            audit_records=ctx.audit_trail.records,
            errors=ctx.errors,
            duration_seconds=0.0,
        )

    # -------------------------------------------------------------------------
    # Accessor methods
    # -------------------------------------------------------------------------

    def get_interpreter(self, workflow_id: str) -> PipelineInterpreter | None:
        """Get the interpreter for an active workflow."""
        return self._interpreters.get(workflow_id)

    def get_orchestrator(self, workflow_id: str) -> DerivationOrchestrator | None:
        """Backward-compat shim — always returns None (pipeline path is now default)."""
        return None

    def get_context(self, workflow_id: str) -> PipelineContext | None:
        """Get the pipeline context for an active workflow."""
        return self._contexts.get(workflow_id)

    def get_fsm(self, workflow_id: str) -> PipelineFSM | None:
        """Get the FSM tracker for an active or completed workflow."""
        return self._fsms.get(workflow_id)

    def get_approval_event(self, workflow_id: str) -> asyncio.Event | None:
        """Find the pending HITL gate asyncio.Event, if any."""
        ctx = self._contexts.get(workflow_id)
        if ctx is None:
            return None
        for outputs in ctx.step_outputs.values():
            event = outputs.get("_approval_event")
            if isinstance(event, asyncio.Event) and not event.is_set():
                return event
        return None

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
        return workflow_id in self._interpreters or workflow_id in self._history

    @property
    def active_count(self) -> int:
        """Number of currently running workflows."""
        return len(self._active)

    def list_workflow_ids(self) -> list[str]:
        """All known workflow IDs (active + completed + historic)."""
        return list({*self._active.keys(), *self._results.keys(), *self._history.keys()})

    async def delete_workflow(self, workflow_id: str, state_repo: WorkflowStateRepository) -> None:
        """Remove a workflow from all in-memory stores and delete its DB state."""
        self._interpreters.pop(workflow_id, None)
        self._contexts.pop(workflow_id, None)
        self._fsms.pop(workflow_id, None)
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
