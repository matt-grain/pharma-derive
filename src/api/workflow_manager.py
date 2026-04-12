"""Workflow lifecycle manager — starts background tasks, tracks runs."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from src.api.workflow_serializer import HistoricState, build_result, serialize_ctx
from src.config.settings import get_settings
from src.domain.enums import AgentName, AuditAction, WorkflowStep
from src.factory import create_pipeline_orchestrator

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.domain.workflow_models import WorkflowResult
    from src.engine.pipeline_context import PipelineContext
    from src.engine.pipeline_fsm import PipelineFSM
    from src.engine.pipeline_interpreter import PipelineInterpreter
    from src.persistence.workflow_state_repo import WorkflowStateRepository

# Re-export under the private name tests reference; HistoricState is the canonical name.
_HistoricState = HistoricState


def _persist_audit_trail(ctx: PipelineContext, output_dir: Path) -> None:
    """Write the audit trail as JSON to output/{wf_id}_audit.json.

    Runs in the finally block of _run_and_cleanup so the file is written
    regardless of whether the pipeline succeeded, failed, or raised mid-step.
    Best-effort: a write failure is logged but does not mask the original exception.
    """
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        audit_path = output_dir / f"{ctx.workflow_id}_audit.json"
        records = [rec.model_dump(mode="json") for rec in ctx.audit_trail.records]
        audit_path.write_text(json.dumps(records, indent=2, default=str), encoding="utf-8")
    except Exception:
        logger.exception("Failed to persist audit trail for {wf_id}", wf_id=ctx.workflow_id)


async def _persist_error_state(
    wf_id: str,
    ctx: PipelineContext,
    session: AsyncSession,
    started_at: str | None = None,
    completed_at: str | None = None,
) -> None:
    """Best-effort persist of failed workflow state — rolls back on failure."""
    from src.persistence.workflow_state_repo import WorkflowStateRepository

    try:
        state_repo = WorkflowStateRepository(session)
        await state_repo.save(
            workflow_id=wf_id,
            state_json=serialize_ctx(ctx, WorkflowStep.FAILED.value, started_at=started_at, completed_at=completed_at),
            fsm_state=WorkflowStep.FAILED.value,
        )
        await session.commit()
    # Intentional swallow: already in the error-handling path; if persisting
    # the error state itself fails, log and return rather than crash the caller.
    except Exception:
        logger.exception("Failed to persist error state for {wf_id}", wf_id=wf_id)
        await session.rollback()


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
        """Run the pipeline interpreter, persist state, store result."""
        from src.persistence.workflow_state_repo import WorkflowStateRepository

        state_repo = WorkflowStateRepository(session)

        async def _checkpoint(step_id: str) -> None:
            """Persist current FSM + context snapshot so the run survives a restart."""
            try:
                await state_repo.save(
                    workflow_id=wf_id,
                    state_json=serialize_ctx(
                        ctx,
                        fsm.current_state_value,
                        started_at=self._started_at.get(wf_id),
                    ),
                    fsm_state=fsm.current_state_value,
                )
                await session.commit()
                logger.debug(
                    "Checkpointed {wf_id} after step {step_id} (state={state})",
                    wf_id=wf_id,
                    step_id=step_id,
                    state=fsm.current_state_value,
                )
            # Best-effort: a checkpoint failure must not abort the run — log and roll back
            # so the long-lived session stays usable for the final save.
            except Exception:
                logger.exception("Checkpoint failed for {wf_id} at step {step_id}", wf_id=wf_id, step_id=step_id)
                await session.rollback()

        try:
            await interpreter.run(on_step_complete=_checkpoint)
            fsm.complete()
            # Capture completion time BEFORE the final save so the serialized row
            # has a real completed_at — the finally block runs too late for this.
            self._completed_at[wf_id] = datetime.now(UTC).isoformat()
            await state_repo.save(
                workflow_id=wf_id,
                state_json=serialize_ctx(
                    ctx,
                    fsm.current_state_value,
                    started_at=self._started_at.get(wf_id),
                    completed_at=self._completed_at.get(wf_id),
                ),
                fsm_state=fsm.current_state_value,
            )
            await session.commit()
            result = build_result(wf_id, ctx, fsm)
            self._results[wf_id] = result
            logger.info("Workflow {wf_id} completed successfully", wf_id=wf_id)
            return result
        except Exception as exc:
            logger.exception("Workflow {wf_id} failed", wf_id=wf_id)
            ctx.audit_trail.record(
                variable="",
                action=AuditAction.WORKFLOW_FAILED,
                agent=AgentName.ORCHESTRATOR,
                details={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "failed_step": interpreter.current_step or "",
                },
            )
            fsm.fail(str(exc))
            # Same reasoning as the success path — capture completion time before
            # persisting so the DB row has a real completed_at.
            self._completed_at[wf_id] = datetime.now(UTC).isoformat()
            await _persist_error_state(
                wf_id,
                ctx,
                session,
                started_at=self._started_at.get(wf_id),
                completed_at=self._completed_at[wf_id],
            )
            raise
        finally:
            # Only fill in if the success/error paths didn't already set it — they
            # capture the timestamp BEFORE their respective DB save so the row has
            # a real completed_at on disk. This setdefault is the fallback for any
            # path that skipped both (shouldn't happen, but is cheap insurance).
            self._completed_at.setdefault(wf_id, datetime.now(UTC).isoformat())
            _persist_audit_trail(ctx, Path(get_settings().output_dir))
            await session.close()
            self._active.pop(wf_id, None)
            self._sessions.pop(wf_id, None)

    def get_interpreter(self, workflow_id: str) -> PipelineInterpreter | None:
        """Get the interpreter for an active workflow."""
        return self._interpreters.get(workflow_id)

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

    def get_started_at(self, workflow_id: str) -> str | None:
        """Return ISO 8601 start timestamp for an active or completed workflow."""
        return self._started_at.get(workflow_id)

    def get_completed_at(self, workflow_id: str) -> str | None:
        """Return ISO 8601 completion timestamp once the workflow has finished."""
        return self._completed_at.get(workflow_id)

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
        """All known workflow IDs (active, completed, failed, and historic).

        Uses ``_interpreters`` rather than ``_active`` because ``_active`` only
        tracks RUNNING tasks — failed workflows are popped from it in the
        ``finally`` block of ``_run_and_cleanup`` but their ctx/fsm remain in
        memory, so they must stay visible in listings until the next restart.
        """
        return list({*self._interpreters.keys(), *self._results.keys(), *self._history.keys()})

    async def rerun_workflow(self, workflow_id: str) -> str:
        """Restart a workflow: start a fresh run with the same spec, then delete the old one.

        Resolves the source spec from the in-memory context when available, otherwise
        falls back to the historic DB row (which carries ``spec_path``). The old workflow
        is only deleted after the new one has successfully started, so a spec-resolution
        failure leaves the original untouched. Raises ``KeyError`` if the spec path
        cannot be recovered.
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
        """Remove a workflow from in-memory stores, DB state, and output files.

        File cleanup lives here (rather than at the router layer) so that all callers
        — the ``DELETE /workflows/{id}`` endpoint AND the ``rerun_workflow`` flow that
        drops the old run — get the same cleanup behavior.
        """
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

    async def cancel_active(self) -> None:
        """Cancel all running workflows. Used for graceful shutdown and test cleanup."""
        tasks = list(self._active.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
