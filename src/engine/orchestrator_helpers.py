"""Pure helper functions for the orchestrator — serialization, result building, audit details."""

from __future__ import annotations

import json

from src.audit.trail import AuditTrail  # noqa: TC001 — used at runtime in function body
from src.domain.models import (
    DAGNode,
    DerivationStatus,
    QCVerdict,
    WorkflowStep,
)
from src.domain.workflow_fsm import WorkflowFSM  # noqa: TC001 — used at runtime in function body
from src.domain.workflow_models import WorkflowResult, WorkflowState, WorkflowStatus


def serialize_workflow_state(state: WorkflowState, fsm_state: str) -> str:
    """Serialize workflow state including DAG nodes for DB persistence."""
    dag = state.dag
    dag_nodes: dict[str, dict[str, object]] = {}
    if dag:
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
            "workflow_id": state.workflow_id,
            "status": fsm_state,
            "study": state.spec.metadata.study if state.spec else None,
            "derived_variables": list(dag.nodes if dag else {}),
            "errors": state.errors,
            "dag_nodes": dag_nodes,
        }
    )


def build_workflow_result(
    state: WorkflowState,
    fsm: WorkflowFSM,
    audit_trail: AuditTrail,
    elapsed: float,
) -> WorkflowResult:
    """Build the immutable WorkflowResult from final state."""
    dag = state.dag
    qc = (
        {v: (n.qc_verdict.value if n.qc_verdict else DerivationStatus.PENDING.value) for v, n in dag.nodes.items()}
        if dag
        else {}
    )
    derived = [v for v, n in dag.nodes.items() if n.status == DerivationStatus.APPROVED] if dag else []
    is_done = fsm.current_state_value == WorkflowStep.COMPLETED.value
    return WorkflowResult(
        workflow_id=state.workflow_id,
        study=state.spec.metadata.study if state.spec else "unknown",
        status=WorkflowStatus.COMPLETED if is_done else WorkflowStatus.FAILED,
        derived_variables=derived,
        qc_summary=qc,
        audit_records=audit_trail.records + fsm.audit_records,
        audit_summary=state.audit_summary,
        errors=state.errors,
        duration_seconds=round(elapsed, 3),
    )


def build_derivation_details(node: DAGNode) -> dict[str, str | int | float | bool | None]:
    """Build audit details dict with resolution context for a completed derivation."""
    details: dict[str, str | int | float | bool | None] = {
        "status": node.status.value,
        "qc_verdict": node.qc_verdict.value if node.qc_verdict else None,
    }
    if node.qc_verdict == QCVerdict.MISMATCH and node.status == DerivationStatus.APPROVED:
        if node.approved_code == node.coder_code:
            details["resolution"] = "debugger resolved — coder version approved"
        elif node.approved_code == node.qc_code:
            details["resolution"] = "debugger resolved — QC version approved"
        else:
            details["resolution"] = "debugger resolved — fix applied"
        if node.debug_analysis:
            details["debug_root_cause"] = node.debug_analysis
    elif node.qc_verdict == QCVerdict.MATCH:
        details["resolution"] = "QC match — coder version auto-approved"
    return details
