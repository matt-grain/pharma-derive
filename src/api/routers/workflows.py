"""Workflow endpoints — start, monitor, and retrieve derivation run results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

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
from src.config.settings import get_settings

if TYPE_CHECKING:
    from src.domain.dag import DerivationDAG

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])


@router.post("/", response_model=WorkflowCreateResponse, status_code=202)
async def start_workflow(
    payload: WorkflowCreateRequest,
    manager: WorkflowManagerDep,
) -> WorkflowCreateResponse:
    """Start a new derivation workflow as a background task."""
    # Normalize: accept both "simple_mock.yaml" and "specs/simple_mock.yaml"
    spec_path = payload.spec_path
    if not spec_path.startswith("specs/"):
        spec_path = f"specs/{spec_path}"
    wf_id = await manager.start_workflow(
        spec_path=spec_path,
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


@router.post("/{workflow_id}/approve", status_code=200)
async def approve_workflow(workflow_id: str, manager: WorkflowManagerDep) -> WorkflowStatusResponse:
    """Approve a workflow at the HITL review gate — releases it to proceed to audit."""
    orch = manager.get_orchestrator(workflow_id)
    if orch is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id!r} not found")
    if not orch.awaiting_approval:
        raise HTTPException(status_code=409, detail="Workflow is not awaiting approval")
    orch.approve()
    return _build_status_response(workflow_id, manager)


@router.delete("/{workflow_id}", status_code=204)
async def delete_workflow(workflow_id: str, manager: WorkflowManagerDep) -> None:
    """Delete a workflow from history. Removes DB state and output files."""
    if not manager.is_known(workflow_id):
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id!r} not found")
    await manager.delete_workflow(workflow_id)
    # Clean up output files
    output_dir = Path(get_settings().output_dir)
    for suffix in ("_audit.json", "_adam.csv"):
        path = output_dir / f"{workflow_id}{suffix}"
        if path.exists():
            path.unlink()


@router.get("/{workflow_id}", response_model=WorkflowStatusResponse, status_code=200)
async def get_workflow_status(
    workflow_id: str,
    manager: WorkflowManagerDep,
) -> WorkflowStatusResponse:
    """Get the current status of a single workflow."""
    if not manager.is_known(workflow_id):
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id!r} not found")
    return _build_status_response(workflow_id, manager)


@router.get("/{workflow_id}/result", response_model=WorkflowResultResponse, status_code=200)
async def get_workflow_result(
    workflow_id: str,
    manager: WorkflowManagerDep,
) -> WorkflowResultResponse:
    """Return the full result for a completed workflow (409 if still running)."""
    if manager.is_running(workflow_id):
        raise HTTPException(status_code=409, detail="Workflow is still running")

    # In-memory result (current session)
    result = manager.get_result(workflow_id)
    if result is not None:
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

    # Fallback: reconstruct from DB history
    hist = manager.get_historic(workflow_id)
    if hist is not None:
        qc_summary = {var: str(node.get("qc_verdict", "unknown")) for var, node in hist.dag_nodes.items()}
        return WorkflowResultResponse(
            workflow_id=workflow_id,
            study=hist.study or "unknown",
            status=hist.fsm_state,
            derived_variables=hist.derived_variables,
            qc_summary=qc_summary,
            errors=hist.errors,
            duration_seconds=0.0,
        )

    raise HTTPException(status_code=404, detail=f"Workflow {workflow_id!r} not found")


@router.get("/{workflow_id}/audit", response_model=list[AuditRecordOut], status_code=200)
async def get_workflow_audit(
    workflow_id: str,
    manager: WorkflowManagerDep,
) -> list[AuditRecordOut]:
    """Return the full audit trail — from memory or from persisted JSON file."""
    orch = manager.get_orchestrator(workflow_id)
    if orch is not None:
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

    # Fallback: load from persisted audit JSON file
    audit_path = Path(get_settings().output_dir) / f"{workflow_id}_audit.json"
    if audit_path.exists():
        records = json.loads(audit_path.read_text(encoding="utf-8"))
        return [AuditRecordOut(**r) for r in records]

    if not manager.is_known(workflow_id):
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id!r} not found")
    return []


@router.get("/{workflow_id}/adam", status_code=200)
async def download_adam(workflow_id: str) -> FileResponse:
    """Download the derived ADaM CSV file."""
    adam_path = Path(get_settings().output_dir) / f"{workflow_id}_adam.csv"
    if not adam_path.exists():
        raise HTTPException(status_code=404, detail=f"ADaM file not found for workflow {workflow_id!r}")
    return FileResponse(adam_path, media_type="text/csv", filename=f"{workflow_id}_adam.csv")


@router.get("/{workflow_id}/dag", response_model=list[DAGNodeOut], status_code=200)
async def get_workflow_dag(
    workflow_id: str,
    manager: WorkflowManagerDep,
) -> list[DAGNodeOut]:
    """Return all DAG nodes — from memory or from persisted DB state."""
    orch = manager.get_orchestrator(workflow_id)
    if orch is not None:
        dag = orch.state.dag
        if dag is None:
            return []
        return [_dag_node_out(dag, var) for var in dag.execution_order]

    # Fallback: load from persisted dag_nodes in DB history
    hist = manager.get_historic(workflow_id)
    if hist is not None and hist.dag_nodes:
        return [
            DAGNodeOut(
                variable=var,
                status=str(node.get("status", "unknown")),
                layer=int(node.get("layer") or 0),  # type: ignore[arg-type]  # JSON parsed as object
                coder_code=node.get("coder_code"),  # type: ignore[arg-type]  # dict values are object
                qc_code=node.get("qc_code"),  # type: ignore[arg-type]
                qc_verdict=node.get("qc_verdict"),  # type: ignore[arg-type]
                approved_code=node.get("approved_code"),  # type: ignore[arg-type]
                dependencies=list(node.get("dependencies", [])),  # type: ignore[arg-type]
            )
            for var, node in hist.dag_nodes.items()
        ]

    if not manager.is_known(workflow_id):
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id!r} not found")
    return []


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
    """Build a WorkflowStatusResponse from orchestrator, result, or DB history."""
    orch = manager.get_orchestrator(workflow_id)
    if orch is not None:
        status = str(orch.fsm.current_state_value or "unknown")
        state = orch.state
        result = manager.get_result(workflow_id)
        return WorkflowStatusResponse(
            workflow_id=workflow_id,
            status=status,
            study=state.spec.metadata.study if state.spec else None,
            awaiting_approval=orch.awaiting_approval,
            started_at=state.started_at,
            completed_at=state.completed_at,
            derived_variables=result.derived_variables if result else list(state.dag.nodes.keys()) if state.dag else [],
            errors=result.errors if result else state.errors,
        )

    # Fallback to DB history (survives restarts)
    hist = manager.get_historic(workflow_id)
    if hist is not None:
        return WorkflowStatusResponse(
            workflow_id=workflow_id,
            status=hist.fsm_state,
            study=hist.study,
            derived_variables=hist.derived_variables,
            errors=hist.errors,
        )

    return WorkflowStatusResponse(workflow_id=workflow_id, status="unknown")
