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
    """Write per-variable feedback rows then set the approval event."""
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
