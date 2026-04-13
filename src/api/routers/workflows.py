"""Workflow endpoints — start, monitor, and retrieve derivation run results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException

from src.api.dependencies import (
    WorkflowManagerDep,  # noqa: TC001 — FastAPI resolves Annotated[Depends] at runtime via get_type_hints()
)
from src.api.schemas import (
    AuditRecordOut,
    DAGNodeOut,
    SourceColumnOut,
    WorkflowCreateRequest,
    WorkflowCreateResponse,
    WorkflowResultResponse,
    WorkflowStatusResponse,
)
from src.config.settings import get_settings
from src.domain.enums import WorkflowStep

if TYPE_CHECKING:
    from src.domain.dag import DerivationDAG
    from src.engine.pipeline_context import PipelineContext

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
        status=WorkflowStep.RUNNING.value,
        message="Workflow started",
    )


@router.get("/", response_model=list[WorkflowStatusResponse], status_code=200)
async def list_workflows(manager: WorkflowManagerDep) -> list[WorkflowStatusResponse]:
    """List all known workflow IDs with their current status."""
    return [_build_status_response(wf_id, manager) for wf_id in manager.list_workflow_ids()]


@router.delete("/{workflow_id}", status_code=204)
async def delete_workflow(workflow_id: str, manager: WorkflowManagerDep) -> None:
    """Delete a workflow from history. In-memory state, DB row, and output files."""
    if not manager.is_known(workflow_id):
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id!r} not found")
    await manager.delete_workflow(workflow_id)


@router.post("/{workflow_id}/rerun", response_model=WorkflowCreateResponse, status_code=202)
async def rerun_workflow(workflow_id: str, manager: WorkflowManagerDep) -> WorkflowCreateResponse:
    """Start a new workflow using the same spec as an existing one."""
    if not manager.is_known(workflow_id):
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id!r} not found")
    try:
        new_id = await manager.rerun_workflow(workflow_id)
    except KeyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return WorkflowCreateResponse(
        workflow_id=new_id,
        status=WorkflowStep.RUNNING.value,
        message=f"Restarted {workflow_id} as {new_id} (old run deleted)",
    )


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
    ctx = manager.get_context(workflow_id)
    if ctx is not None:
        return [
            AuditRecordOut(
                timestamp=rec.timestamp,
                workflow_id=rec.workflow_id,
                variable=rec.variable,
                action=rec.action,
                agent=rec.agent,
                details=rec.details,
            )
            for rec in ctx.audit_trail.records
        ]

    # Fallback: load from persisted audit JSON file
    audit_path = Path(get_settings().output_dir) / f"{workflow_id}_audit.json"
    if audit_path.exists():
        records = json.loads(audit_path.read_text(encoding="utf-8"))
        return [AuditRecordOut(**r) for r in records]

    if not manager.is_known(workflow_id):
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id!r} not found")
    return []


@router.get("/{workflow_id}/dag", response_model=list[DAGNodeOut], status_code=200)
async def get_workflow_dag(
    workflow_id: str,
    manager: WorkflowManagerDep,
) -> list[DAGNodeOut]:
    """Return all DAG nodes — from memory or from persisted DB state."""
    ctx = manager.get_context(workflow_id)
    if ctx is not None:
        dag = ctx.dag
        if dag is None:
            return []
        return [_dag_node_out(dag, var, ctx) for var in dag.execution_order]

    # Fallback: load from persisted dag_nodes in DB history
    hist = manager.get_historic(workflow_id)
    if hist is not None and hist.dag_nodes:
        derived_names = set(hist.dag_nodes.keys())
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
                source_columns=_build_source_cols(
                    rule_source_columns=list(node.get("source_columns", [])),  # type: ignore[arg-type]
                    derived_names=derived_names,
                    column_domain_map=hist.source_column_domains,
                ),
            )
            for var, node in hist.dag_nodes.items()
        ]

    if not manager.is_known(workflow_id):
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id!r} not found")
    return []


def _build_source_cols(
    rule_source_columns: list[str],
    derived_names: set[str],
    column_domain_map: dict[str, str],
) -> list[SourceColumnOut]:
    """Build SourceColumnOut list from rule source columns, skipping derived variables.

    Shared by the live path (ctx.source_column_domains) and the historic path
    (hist.source_column_domains) so both produce consistent output.
    """
    return [
        SourceColumnOut(name=col, domain=column_domain_map.get(col, ""))
        for col in rule_source_columns
        if col not in derived_names
    ]


def _dag_node_out(dag: DerivationDAG, var: str, ctx: PipelineContext | None = None) -> DAGNodeOut:
    """Convert a single DAG node to its API schema."""
    node = dag.get_node(var)
    qc_verdict = node.qc_verdict.value if node.qc_verdict is not None else None
    derived_names = set(dag.nodes.keys())
    domain_map = ctx.source_column_domains if ctx is not None else {}
    source_cols = _build_source_cols(node.rule.source_columns, derived_names, domain_map)
    return DAGNodeOut(
        variable=var,
        status=node.status.value,
        layer=node.layer,
        coder_code=node.coder_code,
        qc_code=node.qc_code,
        qc_verdict=qc_verdict,
        approved_code=node.approved_code,
        dependencies=dag.get_dependencies(var),
        source_columns=source_cols,
    )


def _build_status_response(workflow_id: str, manager: WorkflowManagerDep) -> WorkflowStatusResponse:
    """Build a WorkflowStatusResponse from context+FSM or DB history."""
    ctx = manager.get_context(workflow_id)
    fsm = manager.get_fsm(workflow_id)
    if ctx is not None and fsm is not None:
        status = fsm.current_state_value
        result = manager.get_result(workflow_id)
        awaiting = manager.get_approval_event(workflow_id) is not None
        return WorkflowStatusResponse(
            workflow_id=workflow_id,
            status=status,
            study=ctx.spec.metadata.study if ctx.spec else None,
            awaiting_approval=awaiting,
            started_at=manager.get_started_at(workflow_id),
            completed_at=manager.get_completed_at(workflow_id),
            derived_variables=result.derived_variables if result else list(ctx.dag.nodes.keys()) if ctx.dag else [],
            errors=result.errors if result else ctx.errors,
        )

    # Fallback to DB history (survives restarts)
    hist = manager.get_historic(workflow_id)
    if hist is not None:
        return WorkflowStatusResponse(
            workflow_id=workflow_id,
            status=hist.fsm_state,
            study=hist.study,
            started_at=manager.get_started_at(workflow_id) or hist.started_at,
            completed_at=manager.get_completed_at(workflow_id) or hist.completed_at,
            derived_variables=hist.derived_variables,
            errors=hist.errors,
        )

    return WorkflowStatusResponse(workflow_id=workflow_id, status=WorkflowStep.UNKNOWN.value)
