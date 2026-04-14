"""HITL helpers for WorkflowManager — approve, reject, and session accessor.

Extracted from WorkflowManager to keep the class under the 230-line class limit.
These functions operate on the manager's internal dicts directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession

    from src.api.schemas import ApprovalRequest
    from src.engine.pipeline_context import PipelineContext


async def approve_with_feedback_impl(
    approval_event: asyncio.Event,
    session: AsyncSession | None,
    ctx: PipelineContext | None,
    payload: ApprovalRequest | None,
) -> None:
    """Write per-variable feedback rows, stash approval details on ctx, then set the approval event.

    The stashed fields (`approval_reason`, `approval_approved_vars`, `approval_rejected_vars`) are
    read by `HITLGateStepExecutor` after `event.wait()` returns, so the `HUMAN_APPROVED` audit
    record can carry the full per-variable breakdown instead of just the gate name.
    """
    if payload is not None and ctx is not None:
        ctx.approval_reason = payload.reason or ""
        ctx.approval_approved_vars = [d.variable for d in payload.variables if d.approved]
        ctx.approval_rejected_vars = [d.variable for d in payload.variables if not d.approved]

    if payload is not None and session is not None and ctx is not None and ctx.spec is not None:
        from src.persistence.feedback_repo import FeedbackRepository

        repo = FeedbackRepository(session)
        study = ctx.spec.metadata.study
        for decision in payload.variables:
            await repo.store(
                variable=decision.variable,
                feedback=decision.note or payload.reason or "",
                action_taken="approved" if decision.approved else "rejected",
                study=study,
            )
        await session.commit()
    approval_event.set()


async def reject_workflow_impl(
    ctx: PipelineContext,
    approval_event: asyncio.Event,
    session: AsyncSession | None,
    reason: str,
) -> None:
    """Set the rejection flag, write a feedback row, then release the gate."""
    ctx.rejection_requested = True
    ctx.rejection_reason = reason

    if session is not None and ctx.spec is not None:
        from src.persistence.feedback_repo import FeedbackRepository

        repo = FeedbackRepository(session)
        await repo.store(
            variable="",
            feedback=reason,
            action_taken="rejected",
            study=ctx.spec.metadata.study,
        )
        await session.commit()

    approval_event.set()
