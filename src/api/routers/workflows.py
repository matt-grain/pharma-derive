"""Workflow endpoints — start, monitor, and retrieve derivation run results."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException

from src.api.dependencies import (
    WorkflowManagerDep,  # noqa: TC001 — FastAPI resolves Annotated[Depends] at runtime via get_type_hints()
)
from src.api.schemas import (
    AuditRecordOut,
    DAGNodeOut,
    WorkflowCreateRequest,
    WorkflowCreateResponse,
    WorkflowResultResponse,
    WorkflowStatusResponse,
)

if TYPE_CHECKING:
    from src.domain.dag import DerivationDAG

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])


@router.post("/", response_model=WorkflowCreateResponse, status_code=202)
async def start_workflow(
    payload: WorkflowCreateRequest,
    manager: WorkflowManagerDep,
) -> WorkflowCreateResponse:
    """Start a new derivation workflow as a background task."""
    wf_id = await manager.start_workflow(
        spec_path=payload.spec_path,
        llm_base_url=payload.llm_base_url,
    )
    return WorkflowCreateResponse(
        workflow_id=wf_id,
        status="running",
        message="Workflow started",
    )


@router.get("/", response_model=list[WorkflowStatusResponse], status_code=200)
async def list_workflows(manager: WorkflowManagerDep) -> list[WorkflowStatusResponse]:
    """List all known workflow IDs with their current status."""
    return [_build_status_response(wf_id, manager) for wf_id in manager.list_workflow_ids()]


@router.get("/{workflow_id}", response_model=WorkflowStatusResponse, status_code=200)
async def get_workflow_status(
    workflow_id: str,
    manager: WorkflowManagerDep,
) -> WorkflowStatusResponse:
    """Get the current status of a single workflow."""
    if manager.get_orchestrator(workflow_id) is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id!r} not found")
    return _build_status_response(workflow_id, manager)


@router.get("/{workflow_id}/result", response_model=WorkflowResultResponse, status_code=200)
async def get_workflow_result(
    workflow_id: str,
    manager: WorkflowManagerDep,
) -> WorkflowResultResponse:
    """Return the full result for a completed workflow (409 if still running)."""
    if manager.get_orchestrator(workflow_id) is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id!r} not found")
    if manager.is_running(workflow_id):
        raise HTTPException(status_code=409, detail="Workflow is still running")
    result = manager.get_result(workflow_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No result for workflow {workflow_id!r}")
    return WorkflowResultResponse(
        workflow_id=result.workflow_id,
        study=result.study,
        status=result.status.value,
        derived_variables=result.derived_variables,
        qc_summary=result.qc_summary,
        audit_summary=result.audit_summary.model_dump() if result.audit_summary else None,
        errors=result.errors,
        duration_seconds=result.duration_seconds,
    )


@router.get("/{workflow_id}/audit", response_model=list[AuditRecordOut], status_code=200)
async def get_workflow_audit(
    workflow_id: str,
    manager: WorkflowManagerDep,
) -> list[AuditRecordOut]:
    """Return the full audit trail for a workflow."""
    orch = manager.get_orchestrator(workflow_id)
    if orch is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id!r} not found")
    return [
        AuditRecordOut(
            timestamp=rec.timestamp,
            workflow_id=rec.workflow_id,
            variable=rec.variable,
            action=rec.action,
            agent=rec.agent,
            details=rec.details,
        )
        for rec in orch.audit_trail.records
    ]


@router.get("/{workflow_id}/dag", response_model=list[DAGNodeOut], status_code=200)
async def get_workflow_dag(
    workflow_id: str,
    manager: WorkflowManagerDep,
) -> list[DAGNodeOut]:
    """Return all DAG nodes with their current derivation status."""
    orch = manager.get_orchestrator(workflow_id)
    if orch is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id!r} not found")
    dag = orch.state.dag
    if dag is None:
        return []
    return [_dag_node_out(dag, var) for var in dag.execution_order]


def _dag_node_out(dag: DerivationDAG, var: str) -> DAGNodeOut:
    """Convert a single DAG node to its API schema."""
    node = dag.get_node(var)
    qc_verdict = node.qc_verdict.value if node.qc_verdict is not None else None
    return DAGNodeOut(
        variable=var,
        status=node.status.value,
        layer=node.layer,
        coder_code=node.coder_code,
        qc_code=node.qc_code,
        qc_verdict=qc_verdict,
        approved_code=node.approved_code,
        dependencies=dag.get_dependencies(var),
    )


def _build_status_response(workflow_id: str, manager: WorkflowManagerDep) -> WorkflowStatusResponse:
    """Build a WorkflowStatusResponse from orchestrator and result state."""
    orch = manager.get_orchestrator(workflow_id)
    if orch is None:
        return WorkflowStatusResponse(workflow_id=workflow_id, status="unknown")

    status = str(orch.fsm.current_state_value or "unknown")
    state = orch.state
    result = manager.get_result(workflow_id)

    derived = result.derived_variables if result else []
    errors = result.errors if result else state.errors

    return WorkflowStatusResponse(
        workflow_id=workflow_id,
        status=status,
        started_at=state.started_at,
        completed_at=state.completed_at,
        derived_variables=derived,
        errors=errors,
    )
