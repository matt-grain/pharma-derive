"""HITL (Human-In-The-Loop) endpoints — approve, reject, and override derivations."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.api.dependencies import (
    WorkflowManagerDep,  # noqa: TC001 — FastAPI resolves Annotated[Depends] at runtime via get_type_hints()
)
from src.api.routers.workflows import (
    _build_status_response,  # pyright: ignore[reportPrivateUsage]  # shared helper within api.routers package
)
from src.api.schemas import (
    ApprovalRequest,
    DAGNodeOut,
    RejectionRequest,
    VariableOverrideRequest,
    WorkflowStatusResponse,
)

router = APIRouter(prefix="/api/v1/workflows", tags=["hitl"])


@router.post("/{workflow_id}/approve", response_model=WorkflowStatusResponse, status_code=200)
async def approve_workflow(
    workflow_id: str,
    manager: WorkflowManagerDep,
    payload: ApprovalRequest | None = None,
) -> WorkflowStatusResponse:
    """Approve a workflow at the HITL gate — optionally with per-variable feedback."""
    ctx = manager.get_context(workflow_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id!r} not found")
    try:
        await manager.approve_with_feedback(workflow_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=409, detail="Workflow is not awaiting approval") from exc
    return _build_status_response(workflow_id, manager)


@router.post("/{workflow_id}/reject", response_model=WorkflowStatusResponse, status_code=200)
async def reject_workflow_endpoint(
    workflow_id: str,
    payload: RejectionRequest,
    manager: WorkflowManagerDep,
) -> WorkflowStatusResponse:
    """Reject a workflow at the HITL gate — fails the FSM with the provided reason."""
    try:
        await manager.reject_workflow(workflow_id, payload.reason)
    except KeyError as exc:
        code = 404 if "workflow_not_found" in str(exc) else 409
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _build_status_response(workflow_id, manager)


@router.post(
    "/{workflow_id}/variables/{variable}/override",
    response_model=DAGNodeOut,
    status_code=200,
)
async def override_variable(
    workflow_id: str,
    variable: str,
    payload: VariableOverrideRequest,
    manager: WorkflowManagerDep,
) -> DAGNodeOut:
    """Override a derivation's approved code with human-edited code."""
    ctx = manager.get_context(workflow_id)
    session = manager.get_session(workflow_id)
    if ctx is None or session is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id!r} not found")

    from src.api.services.override_service import OverrideService
    from src.domain.exceptions import DerivationError, NotFoundError

    service = OverrideService(session)
    try:
        return await service.override_variable(ctx, variable, payload.new_code, payload.reason)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DerivationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
