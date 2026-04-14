"""Unit tests for the query_qc_history tool.

Tests cover: no repo, empty DB, results returned, variable filter, and 3-record cap.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pandas as pd
import pytest
from pydantic_ai import RunContext

from src.agents.deps import CoderDeps
from src.agents.tools.query_qc_history import query_qc_history
from src.domain.models import DerivationRule, OutputDType, QCVerdict
from src.persistence.database import init_db
from src.persistence.qc_history_repo import QCHistoryRepository

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@pytest.fixture
async def qc_history_repo() -> AsyncGenerator[QCHistoryRepository]:
    session_factory = await init_db("sqlite+aiosqlite:///:memory:")
    async with session_factory() as session:
        yield QCHistoryRepository(session)


def _make_ctx(rule: DerivationRule, repo: QCHistoryRepository | None) -> RunContext[CoderDeps]:
    """Build a minimal RunContext stub with the given QCHistoryRepository."""
    deps = CoderDeps(
        df=pd.DataFrame({"age": [72, 45]}),
        synthetic_csv="age\n72\n45",
        rule=rule,
        available_columns=["age"],
        qc_history_repo=repo,
    )
    ctx: RunContext[CoderDeps] = MagicMock(spec=RunContext)
    ctx.deps = deps
    return ctx


@pytest.fixture
def agegr1_rule() -> DerivationRule:
    return DerivationRule(
        variable="AGEGR1",
        source_columns=["age"],
        logic="<65 / 65-80 / >80",
        output_type=OutputDType.STR,
    )


@pytest.fixture
def trtdur_rule() -> DerivationRule:
    return DerivationRule(
        variable="TRTDUR",
        source_columns=["treatment_start", "treatment_end"],
        logic="Days between end and start",
        output_type=OutputDType.FLOAT,
        nullable=True,
    )


async def test_query_qc_history_with_no_repo_returns_unavailable_message(
    agegr1_rule: DerivationRule,
) -> None:
    # Arrange
    ctx = _make_ctx(agegr1_rule, repo=None)

    # Act
    result = await query_qc_history(ctx)

    # Assert
    assert result == "No QC history available."


async def test_query_qc_history_with_empty_db_returns_no_history_message(
    qc_history_repo: QCHistoryRepository,
    agegr1_rule: DerivationRule,
) -> None:
    # Arrange
    ctx = _make_ctx(agegr1_rule, repo=qc_history_repo)

    # Act
    result = await query_qc_history(ctx)

    # Assert
    assert result == "No prior QC history for this variable."


async def test_query_qc_history_returns_formatted_rows_when_found(
    qc_history_repo: QCHistoryRepository,
    agegr1_rule: DerivationRule,
) -> None:
    # Arrange — seed 1 match + 1 mismatch row
    await qc_history_repo.store(
        variable="AGEGR1",
        verdict=QCVerdict.MATCH,
        coder_approach="pd.cut approach",
        qc_approach="pd.cut approach",
        study="STUDY01",
    )
    await qc_history_repo.store(
        variable="AGEGR1",
        verdict=QCVerdict.MISMATCH,
        coder_approach="np.select approach",
        qc_approach="pd.cut approach",
        study="STUDY01",
    )
    ctx = _make_ctx(agegr1_rule, repo=qc_history_repo)

    # Act
    result = await query_qc_history(ctx)

    # Assert — both records formatted with correct headers and verdict phrases
    assert "QC HISTORY 1" in result
    assert "QC HISTORY 2" in result
    assert "Coder and QC agreed on this implementation — safe pattern to repeat." in result
    assert "Coder and QC disagreed." in result
    assert "pd.cut approach" in result
    assert "np.select approach" in result


async def test_query_qc_history_respects_variable_filter(
    qc_history_repo: QCHistoryRepository,
    agegr1_rule: DerivationRule,
    trtdur_rule: DerivationRule,
) -> None:
    # Arrange — seed AGEGR1 and TRTDUR rows
    await qc_history_repo.store(
        variable="AGEGR1",
        verdict=QCVerdict.MATCH,
        coder_approach="agegr1_coder",
        qc_approach="agegr1_qc",
        study="STUDY01",
    )
    await qc_history_repo.store(
        variable="TRTDUR",
        verdict=QCVerdict.MATCH,
        coder_approach="trtdur_coder",
        qc_approach="trtdur_qc",
        study="STUDY01",
    )
    ctx = _make_ctx(agegr1_rule, repo=qc_history_repo)

    # Act
    result = await query_qc_history(ctx)

    # Assert — only AGEGR1 row returned, not TRTDUR
    assert "agegr1_coder" in result
    assert "trtdur_coder" not in result


async def test_query_qc_history_caps_at_three_rows(
    qc_history_repo: QCHistoryRepository,
    agegr1_rule: DerivationRule,
) -> None:
    # Arrange — seed 10 rows for AGEGR1
    for i in range(10):
        await qc_history_repo.store(
            variable="AGEGR1",
            verdict=QCVerdict.MATCH,
            coder_approach=f"coder_{i}",
            qc_approach=f"qc_{i}",
            study="STUDY01",
        )
    ctx = _make_ctx(agegr1_rule, repo=qc_history_repo)

    # Act
    result = await query_qc_history(ctx)

    # Assert — exactly 3 records (QC HISTORY 1, 2, 3 — but NOT QC HISTORY 4)
    assert "QC HISTORY 1" in result
    assert "QC HISTORY 2" in result
    assert "QC HISTORY 3" in result
    assert "QC HISTORY 4" not in result
