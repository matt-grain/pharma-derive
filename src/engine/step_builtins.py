"""Builtin pipeline step functions and agent deps builder for step executors.

Extracted from step_executors.py to keep executor classes focused and file sizes
under the 200-line limit. Imported by BuiltinStepExecutor and AgentStepExecutor.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any  # Any: heterogeneous agent dep and callback types

if TYPE_CHECKING:
    from src.domain.pipeline_models import StepDefinition
    from src.engine.pipeline_context import PipelineContext


# ---------------------------------------------------------------------------
# Builtin step functions — each takes (step, ctx) and mutates ctx
# ---------------------------------------------------------------------------


async def _builtin_parse_spec(step: StepDefinition, ctx: PipelineContext) -> None:
    """Parse spec, load source data, generate synthetic CSV — mirrors orchestrator._step_spec_review."""
    from src.domain.source_loader import get_column_domain_map, load_source_data
    from src.domain.spec_parser import parse_spec
    from src.domain.synthetic import generate_synthetic

    spec_path = ctx.step_outputs.get("_init", {}).get("spec_path")
    if spec_path is None:
        msg = f"Step '{step.id}' requires '_init.spec_path' in context"
        raise ValueError(msg)
    ctx.spec = parse_spec(spec_path)
    source_df = load_source_data(ctx.spec)
    ctx.derived_df = source_df.copy()
    ctx.synthetic_csv = generate_synthetic(source_df, rows=ctx.spec.synthetic.rows).to_csv(index=False)
    ctx.source_column_domains = get_column_domain_map(ctx.spec)


async def _builtin_build_dag(step: StepDefinition, ctx: PipelineContext) -> None:
    """Build DerivationDAG from spec and available columns."""
    from src.domain.dag import DerivationDAG
    from src.domain.source_loader import get_source_columns

    if ctx.spec is None or ctx.derived_df is None:
        msg = f"Step '{step.id}' requires spec and derived_df in context"
        raise ValueError(msg)
    ctx.dag = DerivationDAG(ctx.spec.derivations, get_source_columns(ctx.derived_df))


async def _builtin_export_adam(step: StepDefinition, ctx: PipelineContext) -> None:
    """Export derived DataFrame as CSV and optionally Parquet."""
    if ctx.derived_df is None or ctx.output_dir is None:
        return
    ctx.output_dir.mkdir(parents=True, exist_ok=True)
    wf_id = ctx.workflow_id
    ctx.derived_df.to_csv(ctx.output_dir / f"{wf_id}_adam.csv", index=False)
    formats = step.config.get("formats", ["csv"])
    if "parquet" in formats:  # type: ignore[operator]  # config value is str|int|float|bool|list[str]
        ctx.derived_df.to_parquet(ctx.output_dir / f"{wf_id}_adam.parquet", index=False, engine="pyarrow")


async def _builtin_save_patterns(step: StepDefinition, ctx: PipelineContext) -> None:
    """Persist approved DAG nodes to PatternRepository + QC verdicts to QCHistoryRepository."""
    if ctx.session is None or ctx.dag is None or ctx.spec is None:
        return
    from src.domain.models import DerivationStatus
    from src.persistence.pattern_repo import PatternRepository
    from src.persistence.qc_history_repo import QCHistoryRepository

    pattern_repo = PatternRepository(ctx.session)
    qc_repo = QCHistoryRepository(ctx.session)
    study = ctx.spec.metadata.study

    for variable in ctx.dag.execution_order:
        node = ctx.dag.get_node(variable)
        if node.status != DerivationStatus.APPROVED or node.approved_code is None:
            continue
        await pattern_repo.store(
            variable_type=node.rule.variable,
            spec_logic=node.rule.logic,
            approved_code=node.approved_code,
            study=study,
            approach=node.coder_approach or "",
        )
        if node.qc_verdict is not None:
            await qc_repo.store(
                variable=node.rule.variable,
                verdict=node.qc_verdict,
                coder_approach=node.coder_approach or "",
                qc_approach=node.qc_approach or "",
                study=study,
            )
    await ctx.session.commit()


BUILTIN_REGISTRY: dict[str, Any] = {
    "parse_spec": _builtin_parse_spec,
    "build_dag": _builtin_build_dag,
    "export_adam": _builtin_export_adam,
    "save_patterns": _builtin_save_patterns,
}


# ---------------------------------------------------------------------------
# Agent deps builder — dispatches by agent name to construct typed deps
# ---------------------------------------------------------------------------


def _build_spec_interpreter_deps(ctx: PipelineContext) -> tuple[Any, str]:
    from src.agents.deps import SpecInterpreterDeps

    if ctx.spec is None:
        msg = "spec_interpreter requires ctx.spec"
        raise ValueError(msg)
    deps = SpecInterpreterDeps(
        spec_yaml=str(ctx.spec),
        source_columns=list(ctx.derived_df.columns) if ctx.derived_df is not None else [],
    )
    return deps, "Interpret the transformation spec"


def _build_auditor_deps(ctx: PipelineContext) -> tuple[Any, str]:
    from src.agents.deps import AuditorDeps

    if ctx.dag is None or ctx.spec is None:
        msg = "auditor requires ctx.dag and ctx.spec"
        raise ValueError(msg)
    dag_lines = [f"{v}: {ctx.dag.get_node(v).status}" for v in ctx.dag.execution_order]
    deps = AuditorDeps(
        dag_summary="\n".join(dag_lines),
        workflow_id=ctx.workflow_id,
        spec_metadata=ctx.spec.metadata,
    )
    return deps, "Generate audit summary"


_PARALLEL_MAP_ONLY_AGENTS: frozenset[str] = frozenset({"coder", "qc_programmer", "debugger"})

# Registry maps agent name → deps builder. Add new entries here when registering new agents.
AGENT_DEPS_BUILDERS: dict[str, Any] = {
    "spec_interpreter": _build_spec_interpreter_deps,
    "auditor": _build_auditor_deps,
}


def build_agent_deps_and_prompt(
    step: StepDefinition,
    ctx: PipelineContext,
    agent_name: str | None = None,
) -> tuple[Any, str]:
    """Build agent-specific deps and prompt based on agent name."""
    name = agent_name or step.agent or ""

    builder = AGENT_DEPS_BUILDERS.get(name)
    if builder is not None:
        return builder(ctx)
    if name in _PARALLEL_MAP_ONLY_AGENTS:
        msg = f"Agent '{name}' should be invoked via parallel_map, not directly"
        raise ValueError(msg)
    msg = f"No deps builder for agent '{name}'"
    raise ValueError(msg)
