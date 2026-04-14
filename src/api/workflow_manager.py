"""Workflow lifecycle manager — starts background tasks, tracks runs."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from src.api.schemas import (
    ApprovalRequest,  # noqa: TC001 — used at runtime in approve_with_feedback method body (payload.variables)
)
from src.api.workflow_lifecycle import (
    persist_audit_trail,
    persist_error_state,
    persist_success,
    record_failure_audit,
    run_with_checkpoint,
)
from src.api.workflow_serializer import HistoricState, build_result
from src.config.settings import get_settings
from src.domain.exceptions import WorkflowRejectedError
from src.factory import create_pipeline_orchestrator

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.domain.workflow_models import WorkflowResult
    from src.engine.pipeline_context import PipelineContext
    from src.engine.pipeline_fsm import PipelineFSM
    from src.engine.pipeline_interpreter import PipelineInterpreter
    from src.persistence.workflow_state_repo import WorkflowStateRepository

# Tests import this private alias; HistoricState is the canonical name.
_HistoricState = HistoricState


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
        self._started_at: dict[str, str] = {}
        self._completed_at: dict[str, str] = {}

    async def load_history(self, state_repo: WorkflowStateRepository) -> None:
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
        effective_output = output_dir or Path(get_settings().output_dir)
        interpreter, ctx, fsm, session = await create_pipeline_orchestrator(
            spec_path, llm_base_url=llm_base_url, output_dir=effective_output
        )
        wf_id = ctx.workflow_id
        self._interpreters[wf_id] = interpreter
        self._contexts[wf_id] = ctx
        self._fsms[wf_id] = fsm
        self._sessions[wf_id] = session
        self._started_at[wf_id] = datetime.now(UTC).isoformat()
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
        from src.persistence.workflow_state_repo import WorkflowStateRepository

        state_repo = WorkflowStateRepository(session)
        started_at = self._started_at.get(wf_id)
        try:
            await run_with_checkpoint(interpreter, ctx, fsm, session, state_repo, wf_id, started_at)
            fsm.complete()
            self._completed_at[wf_id] = datetime.now(UTC).isoformat()
            await persist_success(state_repo, session, wf_id, ctx, fsm, started_at, self._completed_at[wf_id])
            result = build_result(wf_id, ctx, fsm)
            self._results[wf_id] = result
            logger.info("Workflow {wf_id} completed successfully", wf_id=wf_id)
            return result

        except WorkflowRejectedError as exc:
            # Rejection: log INFO and return (not raise) so the asyncio Task completes cleanly.
            logger.info("Workflow {wf_id} rejected by human: {reason}", wf_id=wf_id, reason=str(exc))
            return await self._fail_and_persist(wf_id, exc, interpreter, ctx, fsm, session, started_at)

        except Exception as exc:
            logger.exception("Workflow {wf_id} failed", wf_id=wf_id)
            await self._fail_and_persist(wf_id, exc, interpreter, ctx, fsm, session, started_at)
            raise
        finally:
            self._completed_at.setdefault(wf_id, datetime.now(UTC).isoformat())
            persist_audit_trail(ctx, Path(get_settings().output_dir))
            await session.close()
            self._active.pop(wf_id, None)
            self._sessions.pop(wf_id, None)

    async def _fail_and_persist(
        self,
        wf_id: str,
        exc: BaseException,
        interpreter: PipelineInterpreter,
        ctx: PipelineContext,
        fsm: PipelineFSM,
        session: AsyncSession,
        started_at: str | None,
    ) -> WorkflowResult:
        from src.persistence.workflow_state_repo import WorkflowStateRepository

        record_failure_audit(ctx, exc, interpreter.current_step)
        fsm.fail(str(exc))
        self._completed_at[wf_id] = datetime.now(UTC).isoformat()
        state_repo = WorkflowStateRepository(session)
        await persist_error_state(state_repo, session, wf_id, ctx, started_at, self._completed_at[wf_id])
        result = build_result(wf_id, ctx, fsm)
        self._results[wf_id] = result
        return result

    def get_interpreter(self, workflow_id: str) -> PipelineInterpreter | None:
        return self._interpreters.get(workflow_id)

    def get_context(self, workflow_id: str) -> PipelineContext | None:
        return self._contexts.get(workflow_id)

    def get_fsm(self, workflow_id: str) -> PipelineFSM | None:
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

    def get_started_at(self, workflow_id: str) -> str | None:
        return self._started_at.get(workflow_id)

    def get_completed_at(self, workflow_id: str) -> str | None:
        return self._completed_at.get(workflow_id)

    def get_historic(self, workflow_id: str) -> _HistoricState | None:
        return self._history.get(workflow_id)

    def get_result(self, workflow_id: str) -> WorkflowResult | None:
        return self._results.get(workflow_id)

    def is_running(self, workflow_id: str) -> bool:
        return workflow_id in self._active

    def is_known(self, workflow_id: str) -> bool:
        """Check if workflow exists in any state (active, completed, or historic)."""
        return workflow_id in self._interpreters or workflow_id in self._history

    @property
    def active_count(self) -> int:
        return len(self._active)

    def list_workflow_ids(self) -> list[str]:
        """All known workflow IDs — active, completed, failed, and historic.

        Uses _interpreters (not _active) because _active is emptied in the finally block
        of _run_and_cleanup, making failed workflows vanish from listings otherwise.
        """
        return list({*self._interpreters.keys(), *self._results.keys(), *self._history.keys()})

    async def rerun_workflow(self, workflow_id: str) -> str:
        """Restart a workflow with the same spec. Resolves spec from ctx or DB history.
        Old workflow is deleted only after the new one starts. Raises KeyError if no spec found.
        """
        spec_path: str | None = None
        ctx = self._contexts.get(workflow_id)
        if ctx is not None:
            init_spec_path = ctx.step_outputs.get("_init", {}).get("spec_path")
            if init_spec_path is not None:
                spec_path = str(init_spec_path)
        if spec_path is None:
            hist = self._history.get(workflow_id)
            if hist is not None and hist.spec_path:
                spec_path = hist.spec_path
        if spec_path is None:
            msg = f"Workflow {workflow_id!r} has no recoverable spec_path — cannot rerun"
            raise KeyError(msg)
        new_id = await self.start_workflow(spec_path)
        # Only reached if start_workflow succeeded — old run is safe to drop.
        await self.delete_workflow(workflow_id)
        return new_id

    async def delete_workflow(self, workflow_id: str) -> None:
        from src.persistence.database import init_db
        from src.persistence.workflow_state_repo import WorkflowStateRepository

        self._interpreters.pop(workflow_id, None)
        self._contexts.pop(workflow_id, None)
        self._fsms.pop(workflow_id, None)
        self._results.pop(workflow_id, None)
        self._history.pop(workflow_id, None)
        self._started_at.pop(workflow_id, None)
        self._completed_at.pop(workflow_id, None)
        session_factory = await init_db()
        async with session_factory() as session:
            state_repo = WorkflowStateRepository(session)
            await state_repo.delete(workflow_id)
            await session.commit()
        output_dir = Path(get_settings().output_dir)
        for suffix in ("_audit.json", "_adam.csv", "_adam.parquet"):
            path = output_dir / f"{workflow_id}{suffix}"
            if path.exists():
                path.unlink()

    def get_session(self, workflow_id: str) -> AsyncSession | None:
        return self._sessions.get(workflow_id)

    async def approve_with_feedback(self, workflow_id: str, payload: ApprovalRequest | None) -> None:
        """Set the HITL approval event AND persist per-variable feedback to the repository."""
        from src.api.workflow_hitl import approve_with_feedback_impl

        event = self.get_approval_event(workflow_id)
        if event is None:
            raise KeyError("not_awaiting_approval")
        await approve_with_feedback_impl(
            event, self._sessions.get(workflow_id), self._contexts.get(workflow_id), payload
        )

    async def reject_workflow(self, workflow_id: str, reason: str) -> None:
        """Flag the workflow for rejection; HITLGateStepExecutor raises WorkflowRejectedError after gate releases."""
        from src.api.workflow_hitl import reject_workflow_impl

        ctx = self._contexts.get(workflow_id)
        if ctx is None:
            raise KeyError("workflow_not_found")
        event = self.get_approval_event(workflow_id)
        if event is None:
            raise KeyError("not_awaiting_approval")
        await reject_workflow_impl(ctx, event, self._sessions.get(workflow_id), reason)

    async def cancel_active(self) -> None:
        tasks = list(self._active.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
