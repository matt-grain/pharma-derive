"""Integration test: long-term memory loop.

Runs a minimal pipeline (parse_spec + build_dag) twice, manually approves all DAG nodes
to simulate post-human-review state, then calls save_patterns. Verifies that patterns
accumulate across runs (cross-run learning) and that query_patterns returns results
on the second run.

No LLM calls — all approvals are injected directly into the DAG.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from src.audit.trail import AuditTrail
from src.domain.models import DerivationRunResult, DerivationStatus, QCVerdict
from src.domain.pipeline_models import PipelineDefinition, StepDefinition, StepType
from src.engine.pipeline_context import PipelineContext
from src.engine.pipeline_interpreter import PipelineInterpreter
from src.engine.step_builtins import BUILTIN_REGISTRY
from src.persistence.database import init_db
from src.persistence.pattern_repo import PatternRepository
from src.persistence.qc_history_repo import QCHistoryRepository

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession


def _make_parse_build_pipeline() -> PipelineDefinition:
    """Minimal pipeline: parse_spec → build_dag (no LLM or HITL steps)."""
    return PipelineDefinition(
        name="ltm_integ_test",
        steps=[
            StepDefinition(id="parse_spec", type=StepType.BUILTIN, builtin="parse_spec"),
            StepDefinition(id="build_dag", type=StepType.BUILTIN, builtin="build_dag", depends_on=["parse_spec"]),
        ],
    )


def _approve_all_dag_nodes(ctx: PipelineContext) -> None:
    """Inject approved status on all DAG nodes to simulate post-human-review state."""
    assert ctx.dag is not None
    for i, variable in enumerate(ctx.dag.execution_order):
        ctx.dag.apply_run_result(
            DerivationRunResult(
                variable=variable,
                status=DerivationStatus.APPROVED,
                approved_code=f"df['{variable}'].fillna(0)  # run-simulated",
                coder_approach=f"approach_{i}",
                qc_approach=f"qc_approach_{i}",
                qc_verdict=QCVerdict.MATCH,
            )
        )


async def _run_and_save(
    spec_path: Path,
    session: AsyncSession,
    wf_id: str,
) -> PipelineContext:
    """Build spec + DAG, simulate HITL approval, persist patterns. Returns final ctx."""
    ctx = PipelineContext(
        workflow_id=wf_id,
        audit_trail=AuditTrail(wf_id),
        llm_base_url="http://localhost:4010",
        pattern_repo=PatternRepository(session),
        qc_history_repo=QCHistoryRepository(session),
    )
    ctx.step_outputs["_init"] = {"spec_path": spec_path}

    # Run parse_spec + build_dag
    await PipelineInterpreter(_make_parse_build_pipeline(), ctx).run()

    # Simulate human review — approve all nodes
    _approve_all_dag_nodes(ctx)

    # Run save_patterns directly
    save_step = StepDefinition(
        id="save_patterns",
        type=StepType.BUILTIN,
        builtin="save_patterns",
        description="Persist approved derivations to long-term memory",
    )
    await BUILTIN_REGISTRY["save_patterns"](save_step, ctx)
    return ctx


async def test_two_runs_of_same_spec_second_run_finds_patterns(
    sample_spec_path: Path,
    tmp_path: Path,
) -> None:
    """Patterns accumulate across two runs; each variable has at least 2 records after run 2."""
    # Arrange — persistent SQLite file shared across both sessions
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'ltm_test.db'}"
    session_factory = await init_db(db_url)

    # Act — run 1
    async with session_factory() as session1:
        ctx1 = await _run_and_save(sample_spec_path, session1, wf_id="run1")

    assert ctx1.dag is not None
    variables = list(ctx1.dag.execution_order)
    n_variables = len(variables)
    assert n_variables > 0

    # Assert — exactly n_variables patterns after run 1
    async with session_factory() as s:
        repo = PatternRepository(s)
        after_run1 = 0
        for v in variables:
            after_run1 += len(await repo.query_by_type(v, limit=10))
    assert after_run1 == n_variables

    # Act — run 2 (same spec, same DB — patterns accumulate)
    async with session_factory() as session2:
        ctx2 = await _run_and_save(sample_spec_path, session2, wf_id="run2")

    assert ctx2.dag is not None

    # Assert — patterns doubled after run 2
    async with session_factory() as s:
        repo = PatternRepository(s)
        after_run2 = 0
        for v in variables:
            after_run2 += len(await repo.query_by_type(v, limit=10))
    assert after_run2 == n_variables * 2

    # Assert — query_patterns tool returns non-empty for each variable after run 2
    from unittest.mock import MagicMock

    import pandas as pd
    from pydantic_ai import RunContext

    from src.agents.deps import CoderDeps
    from src.agents.tools.query_patterns import query_patterns
    from src.domain.models import DerivationRule, OutputDType

    async with session_factory() as s:
        for variable in variables:
            rule = DerivationRule(
                variable=variable,
                source_columns=[],
                logic="test logic",
                output_type=OutputDType.STR,
            )
            deps = CoderDeps(
                df=pd.DataFrame(),
                synthetic_csv="",
                rule=rule,
                available_columns=[],
                pattern_repo=PatternRepository(s),
            )
            ctx_mock: RunContext[CoderDeps] = MagicMock(spec=RunContext)
            ctx_mock.deps = deps
            result = await query_patterns(ctx_mock)
            assert "No prior patterns" not in result, (
                f"Expected patterns for variable '{variable}' after 2 runs, got: {result!r}"
            )
            assert "PATTERN" in result, f"Expected formatted patterns for '{variable}', got: {result!r}"


@pytest.mark.parametrize("pipeline_name", ["express"])
async def test_express_pipeline_does_not_save_patterns(
    sample_spec_path: Path,
    tmp_path: Path,
    pipeline_name: str,
) -> None:
    """Express pipeline has no save_patterns step — patterns table stays empty."""
    from pathlib import Path as _Path

    from src.domain.pipeline_models import load_pipeline

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'express_test.db'}"
    session_factory = await init_db(db_url)

    pipeline_path = _Path(f"config/pipelines/{pipeline_name}.yaml")
    pipeline = load_pipeline(pipeline_path)

    step_ids = {s.id for s in pipeline.steps}
    assert "save_patterns" not in step_ids, (
        f"Express pipeline must not contain save_patterns, but found it in: {step_ids}"
    )

    # Verify patterns table is empty (no step to write to it)
    async with session_factory() as s:
        repo = PatternRepository(s)
        records = await repo.query_by_type("AGE_GROUP", limit=10)
    assert records == []
