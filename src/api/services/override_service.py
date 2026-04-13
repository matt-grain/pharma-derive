"""OverrideService — executes human-edited derivation code and persists the change."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.api.schemas import DAGNodeOut, SourceColumnOut
from src.domain.enums import AgentName, AuditAction
from src.domain.exceptions import DerivationError, NotFoundError
from src.domain.executor import execute_derivation
from src.engine.debug_runner import apply_series_to_df
from src.persistence.feedback_repo import FeedbackRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.domain.dag import DerivationDAG
    from src.engine.pipeline_context import PipelineContext


class OverrideService:
    """Apply a human-provided code override to a DAG node."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def override_variable(
        self,
        ctx: PipelineContext,
        variable: str,
        new_code: str,
        reason: str,
    ) -> DAGNodeOut:
        """Execute new_code, update the DAG node, write audit + feedback row.

        Validates the new code executes successfully BEFORE mutating any state.
        Raises NotFoundError for unknown workflows or variables.
        Raises DerivationError when the new code fails to execute.
        """
        if ctx.dag is None or ctx.derived_df is None:
            raise NotFoundError("workflow_dag", variable)
        if variable not in ctx.dag.nodes:
            raise NotFoundError("variable", variable)

        exec_result = execute_derivation(ctx.derived_df, new_code, list(ctx.derived_df.columns))
        if not exec_result.success:
            raise DerivationError(variable, exec_result.error or "unknown")

        node = ctx.dag.get_node(variable)
        node.approved_code = new_code
        apply_series_to_df(variable, exec_result, ctx.derived_df)
        await self._record_and_persist(ctx, variable, reason)
        return _node_to_schema(ctx.dag, variable, ctx)

    async def _record_and_persist(self, ctx: PipelineContext, variable: str, reason: str) -> None:
        """Write the HUMAN_OVERRIDE audit record and persist the feedback row."""
        ctx.audit_trail.record(
            variable=variable,
            action=AuditAction.HUMAN_OVERRIDE,
            agent=AgentName.HUMAN,
            details={"reason": reason},
        )
        study = ctx.spec.metadata.study if ctx.spec is not None else ""
        await FeedbackRepository(self._session).store(
            variable=variable,
            feedback=reason,
            action_taken="overridden",
            study=study,
        )
        await self._session.commit()


def _node_to_schema(dag: DerivationDAG, variable: str, ctx: PipelineContext) -> DAGNodeOut:
    """Convert the updated DAG node to its DAGNodeOut API schema."""
    node = dag.get_node(variable)
    qc_verdict = node.qc_verdict.value if node.qc_verdict is not None else None
    derived_names = set(dag.nodes.keys())
    domain_map = ctx.source_column_domains
    source_cols = [
        SourceColumnOut(name=col, domain=domain_map.get(col, ""))
        for col in node.rule.source_columns
        if col not in derived_names
    ]
    return DAGNodeOut(
        variable=variable,
        status=node.status.value,
        layer=node.layer,
        coder_code=node.coder_code,
        qc_code=node.qc_code,
        qc_verdict=qc_verdict,
        approved_code=node.approved_code,
        dependencies=dag.get_dependencies(variable),
        source_columns=source_cols,
    )
