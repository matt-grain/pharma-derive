"""Lifecycle helpers for a single pipeline run — extracted from workflow_manager.

Each function owns one transition of the run's lifecycle (checkpoint, success
commit, failure audit, error persist, audit-trail write). Keeping them in a
separate module keeps ``WorkflowManager`` focused on orchestration state and
lets each helper stay short and directly testable.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from loguru import logger

from src.api.workflow_serializer import serialize_ctx
from src.domain.enums import AgentName, AuditAction, WorkflowStep

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession

    from src.engine.pipeline_context import PipelineContext
    from src.engine.pipeline_fsm import PipelineFSM
    from src.engine.pipeline_interpreter import PipelineInterpreter
    from src.persistence.workflow_state_repo import WorkflowStateRepository


def persist_audit_trail(ctx: PipelineContext, output_dir: Path) -> None:
    """Write the audit trail as JSON to ``output/{wf_id}_audit.json``.

    Runs in the ``finally`` block of the run loop so the file is written
    regardless of whether the pipeline succeeded, failed, or raised mid-step.
    A write failure is logged but does not mask the original exception.
    """
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        audit_path = output_dir / f"{ctx.workflow_id}_audit.json"
        records = [rec.model_dump(mode="json") for rec in ctx.audit_trail.records]
        audit_path.write_text(json.dumps(records, indent=2, default=str), encoding="utf-8")
    except Exception:
        logger.exception("Failed to persist audit trail for {wf_id}", wf_id=ctx.workflow_id)


async def run_with_checkpoint(
    interpreter: PipelineInterpreter,
    ctx: PipelineContext,
    fsm: PipelineFSM,
    session: AsyncSession,
    state_repo: WorkflowStateRepository,
    wf_id: str,
    started_at: str | None,
) -> None:
    """Run the pipeline with a per-step checkpoint callback.

    After every step the interpreter fires the callback, which serializes the
    FSM + ctx and commits. A checkpoint failure does not abort the run — it
    logs the exception and rolls back the session so subsequent steps can
    still use it.
    """

    async def checkpoint(step_id: str) -> None:
        try:
            await state_repo.save(
                workflow_id=wf_id,
                state_json=serialize_ctx(ctx, fsm.current_state_value, started_at=started_at),
                fsm_state=fsm.current_state_value,
            )
            await session.commit()
            logger.debug(
                "Checkpointed {wf_id} after step {step_id} (state={state})",
                wf_id=wf_id,
                step_id=step_id,
                state=fsm.current_state_value,
            )
        except Exception:
            logger.exception("Checkpoint failed for {wf_id} at step {step_id}", wf_id=wf_id, step_id=step_id)
            await session.rollback()

    await interpreter.run(on_step_complete=checkpoint)


async def persist_success(
    state_repo: WorkflowStateRepository,
    session: AsyncSession,
    wf_id: str,
    ctx: PipelineContext,
    fsm: PipelineFSM,
    started_at: str | None,
    completed_at: str,
) -> None:
    """Write the final successful state snapshot and commit."""
    await state_repo.save(
        workflow_id=wf_id,
        state_json=serialize_ctx(
            ctx,
            fsm.current_state_value,
            started_at=started_at,
            completed_at=completed_at,
        ),
        fsm_state=fsm.current_state_value,
    )
    await session.commit()


def record_failure_audit(
    ctx: PipelineContext,
    exc: BaseException,
    failed_step: str | None,
) -> None:
    """Append a ``workflow_failed`` record to the audit trail with error details."""
    ctx.audit_trail.record(
        variable="",
        action=AuditAction.WORKFLOW_FAILED,
        agent=AgentName.ORCHESTRATOR,
        details={
            "error": str(exc),
            "error_type": type(exc).__name__,
            "failed_step": failed_step or "",
        },
    )


async def persist_error_state(
    state_repo: WorkflowStateRepository,
    session: AsyncSession,
    wf_id: str,
    ctx: PipelineContext,
    started_at: str | None,
    completed_at: str,
) -> None:
    """Best-effort persist of failed workflow state — rolls back on failure."""
    try:
        await state_repo.save(
            workflow_id=wf_id,
            state_json=serialize_ctx(
                ctx,
                WorkflowStep.FAILED.value,
                started_at=started_at,
                completed_at=completed_at,
            ),
            fsm_state=WorkflowStep.FAILED.value,
        )
        await session.commit()
    # Already in the error-handling path — if persisting the error state itself
    # fails, log and rollback rather than crash the caller.
    except Exception:
        logger.exception("Failed to persist error state for {wf_id}", wf_id=wf_id)
        await session.rollback()
