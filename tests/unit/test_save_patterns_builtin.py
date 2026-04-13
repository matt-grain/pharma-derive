"""Unit tests for the _builtin_save_patterns function.

Tests cover: approved nodes written, non-approved nodes skipped,
QC verdicts written, no-session noop, and empty-DAG noop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
import pytest

from src.audit.trail import AuditTrail
from src.domain.dag import DerivationDAG
from src.domain.models import (
    DerivationRule,
    DerivationRunResult,
    DerivationStatus,
    OutputDType,
    PatternRecord,
    QCVerdict,
    TransformationSpec,
)
from src.engine.pipeline_context import PipelineContext
from src.engine.step_builtins import BUILTIN_REGISTRY
from src.persistence.database import init_db
from src.persistence.pattern_repo import PatternRepository
from src.persistence.qc_history_repo import QCHistoryRepository

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession]:
    session_factory = await init_db("sqlite+aiosqlite:///:memory:")
    async with session_factory() as session:
        yield session


def _minimal_spec_step(step_id: str) -> object:
    from src.domain.pipeline_models import StepDefinition, StepType

    return StepDefinition(id=step_id, type=StepType.BUILTIN, builtin=step_id)


def _make_rules() -> list[DerivationRule]:
    return [
        DerivationRule(variable="AGE_GROUP", source_columns=["age"], logic="<65 adult", output_type=OutputDType.STR),
        DerivationRule(
            variable="TRTDUR",
            source_columns=["treatment_start", "treatment_end"],
            logic="days between",
            output_type=OutputDType.FLOAT,
            nullable=True,
        ),
        DerivationRule(variable="IS_ELDERLY", source_columns=["age"], logic="age >= 65", output_type=OutputDType.BOOL),
    ]


def _make_dag_with_approved_nodes() -> DerivationDAG:
    """Return a 3-node DAG with all nodes in APPROVED status with approved_code set."""
    rules = _make_rules()
    source_cols: set[str] = {"age", "treatment_start", "treatment_end"}
    dag = DerivationDAG(rules, source_cols)

    for i, var in enumerate(dag.execution_order):
        dag.apply_run_result(
            DerivationRunResult(
                variable=var,
                status=DerivationStatus.APPROVED,
                approved_code=f"code_for_{var}",
                coder_approach=f"coder_approach_{i}",
                qc_approach=f"qc_approach_{i}",
                qc_verdict=QCVerdict.MATCH,
            )
        )
    return dag


def _make_ctx(
    dag: DerivationDAG | None = None,
    session: AsyncSession | None = None,
    spec: TransformationSpec | None = None,
) -> PipelineContext:
    from src.domain.models import SourceConfig, SpecMetadata

    ctx = PipelineContext(
        workflow_id="wf-test",
        audit_trail=AuditTrail("wf-test"),
        llm_base_url="http://localhost:4010",
        pattern_repo=PatternRepository(session) if session is not None else None,
        qc_history_repo=QCHistoryRepository(session) if session is not None else None,
    )
    ctx.dag = dag
    ctx.derived_df = pd.DataFrame()

    if spec is not None:
        ctx.spec = spec
    elif dag is not None:
        # Provide minimal spec so the builtin can read study name
        ctx.spec = TransformationSpec(
            metadata=SpecMetadata(study="TEST_STUDY", description="test", version="0.1"),
            source=SourceConfig(format="csv", path="/dev/null", domains=["patients"]),
            derivations=_make_rules(),
        )
    return ctx


# ---------------------------------------------------------------------------
# save_patterns builtin
# ---------------------------------------------------------------------------


async def test_save_patterns_writes_approved_nodes_to_pattern_repo(
    db_session: AsyncSession,
) -> None:
    # Arrange
    dag = _make_dag_with_approved_nodes()
    n_approved = len(dag.execution_order)  # all 3 are approved
    ctx = _make_ctx(dag=dag, session=db_session)
    step = _minimal_spec_step("save_patterns")

    # Act
    await BUILTIN_REGISTRY["save_patterns"](step, ctx)

    # Assert — all 3 approved nodes persisted
    records: list[PatternRecord] = []
    for rule in _make_rules():
        records.extend(await PatternRepository(db_session).query_by_type(rule.variable))
    assert len(records) == n_approved


async def test_save_patterns_skips_non_approved_nodes(
    db_session: AsyncSession,
) -> None:
    # Arrange — DAG with 1 approved, 1 failed, 1 pending
    rules = _make_rules()
    source_cols: set[str] = {"age", "treatment_start", "treatment_end"}
    dag = DerivationDAG(rules, source_cols)

    # Approve only AGE_GROUP
    dag.apply_run_result(
        DerivationRunResult(
            variable="AGE_GROUP",
            status=DerivationStatus.APPROVED,
            approved_code="approved_code",
            coder_approach="cut",
            qc_approach="select",
            qc_verdict=QCVerdict.MATCH,
        )
    )
    # Leave TRTDUR and IS_ELDERLY as PENDING (default)
    ctx = _make_ctx(dag=dag, session=db_session)
    step = _minimal_spec_step("save_patterns")

    # Act
    await BUILTIN_REGISTRY["save_patterns"](step, ctx)

    # Assert — only 1 row in patterns
    age_records = await PatternRepository(db_session).query_by_type("AGE_GROUP")
    trt_records = await PatternRepository(db_session).query_by_type("TRTDUR")
    assert len(age_records) == 1
    assert len(trt_records) == 0


async def test_save_patterns_writes_qc_verdicts_to_qc_history(
    db_session: AsyncSession,
) -> None:
    # Arrange — 3 approved nodes with QC verdicts
    dag = _make_dag_with_approved_nodes()
    ctx = _make_ctx(dag=dag, session=db_session)
    step = _minimal_spec_step("save_patterns")

    # Act
    await BUILTIN_REGISTRY["save_patterns"](step, ctx)

    # Assert — 3 rows in qc_history
    stats = await QCHistoryRepository(db_session).get_stats()
    assert stats.total == 3
    assert stats.matches == 3


async def test_save_patterns_with_no_session_is_noop(
    db_session: AsyncSession,
) -> None:
    # Arrange — session=None, valid dag
    dag = _make_dag_with_approved_nodes()
    ctx = _make_ctx(dag=dag, session=None)
    step = _minimal_spec_step("save_patterns")

    # Act — should not raise
    await BUILTIN_REGISTRY["save_patterns"](step, ctx)

    # Assert — nothing written to the real session (which is separate here)
    records = await PatternRepository(db_session).query_by_type("AGE_GROUP")
    assert records == []


async def test_save_patterns_with_empty_dag_is_noop(
    db_session: AsyncSession,
) -> None:
    # Arrange — DAG with no nodes (empty rules)
    ctx = PipelineContext(
        workflow_id="wf-empty",
        audit_trail=AuditTrail("wf-empty"),
        llm_base_url="http://localhost:4010",
        pattern_repo=PatternRepository(db_session),
        qc_history_repo=QCHistoryRepository(db_session),
    )
    # Leave ctx.dag as None — triggers early return
    step = _minimal_spec_step("save_patterns")

    # Act — should not raise
    await BUILTIN_REGISTRY["save_patterns"](step, ctx)

    # Assert — no writes
    stats = await QCHistoryRepository(db_session).get_stats()
    assert stats.total == 0
