"""Pure serialization helpers — convert PipelineContext / FSM state to API types."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from src.domain.workflow_models import WorkflowResult, WorkflowStatus

if TYPE_CHECKING:
    from src.engine.pipeline_context import PipelineContext
    from src.engine.pipeline_fsm import PipelineFSM


class HistoricState:
    """Lightweight stand-in for a workflow loaded from DB history."""

    def __init__(self, workflow_id: str, fsm_state: str, state_json: str) -> None:
        data = json.loads(state_json)
        self.workflow_id = workflow_id
        self.fsm_state = fsm_state
        self.study: str | None = data.get("study")
        self.derived_variables: list[str] = data.get("derived_variables", [])
        self.errors: list[str] = data.get("errors", [])
        self.dag_nodes: dict[str, dict[str, object]] = data.get("dag_nodes", {})
        # None when loading rows written before this field was added (backward compat)
        self.started_at: str | None = data.get("started_at")
        self.completed_at: str | None = data.get("completed_at")
        # Default {} for backward compat with rows written before this field was added
        self.source_column_domains: dict[str, str] = data.get("source_column_domains", {})
        # Persisted so Rerun works on workflows loaded from history after a backend restart
        self.spec_path: str | None = data.get("spec_path")


def serialize_ctx(
    ctx: PipelineContext,
    fsm_state: str,
    started_at: str | None = None,
    completed_at: str | None = None,
) -> str:
    """Serialize pipeline context to JSON for DB persistence."""
    dag = ctx.dag
    dag_nodes: dict[str, dict[str, object]] = {}
    if dag is not None:
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
                # Persisted so the historic DAG path can rebuild source_columns after restart
                "source_columns": node.rule.source_columns,
            }
    init_spec_path = ctx.step_outputs.get("_init", {}).get("spec_path")
    return json.dumps(
        {
            "workflow_id": ctx.workflow_id,
            "status": fsm_state,
            "study": ctx.spec.metadata.study if ctx.spec else None,
            "derived_variables": list(dag.nodes if dag else {}),
            "errors": ctx.errors,
            "dag_nodes": dag_nodes,
            "started_at": started_at,
            "completed_at": completed_at,
            "source_column_domains": ctx.source_column_domains,
            "spec_path": str(init_spec_path) if init_spec_path is not None else None,
        },
        default=str,
    )


def build_result(wf_id: str, ctx: PipelineContext, fsm: PipelineFSM) -> WorkflowResult:
    """Build immutable WorkflowResult from pipeline context and FSM state."""
    from src.domain.models import DerivationStatus

    dag = ctx.dag
    qc_summary = (
        {v: (n.qc_verdict.value if n.qc_verdict else DerivationStatus.PENDING.value) for v, n in dag.nodes.items()}
        if dag
        else {}
    )
    derived = [v for v, n in dag.nodes.items() if n.status == DerivationStatus.APPROVED] if dag else []
    is_done = fsm.is_terminal and not fsm.is_failed
    return WorkflowResult(
        workflow_id=wf_id,
        study=ctx.spec.metadata.study if ctx.spec else "unknown",
        status=WorkflowStatus.COMPLETED if is_done else WorkflowStatus.FAILED,
        derived_variables=derived,
        qc_summary=qc_summary,
        audit_records=ctx.audit_trail.records,
        errors=ctx.errors,
        duration_seconds=0.0,
    )
