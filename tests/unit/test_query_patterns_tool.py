"""Unit tests for the query_patterns tool.

Tests cover: no session, empty DB, results returned, variable filter, and 3-pattern cap.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pandas as pd
import pytest
from pydantic_ai import RunContext

from src.agents.deps import CoderDeps
from src.agents.tools.query_patterns import query_patterns
from src.domain.models import DerivationRule, OutputDType
from src.persistence.database import init_db
from src.persistence.pattern_repo import PatternRepository

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@pytest.fixture
async def pattern_repo() -> AsyncGenerator[PatternRepository]:
    session_factory = await init_db("sqlite+aiosqlite:///:memory:")
    async with session_factory() as session:
        yield PatternRepository(session)


def _make_ctx(rule: DerivationRule, repo: PatternRepository | None) -> RunContext[CoderDeps]:
    """Build a minimal RunContext stub with the given PatternRepository."""
    deps = CoderDeps(
        df=pd.DataFrame({"age": [72, 45]}),
        synthetic_csv="age\n72\n45",
        rule=rule,
        available_columns=["age"],
        pattern_repo=repo,
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


async def test_query_patterns_with_no_session_returns_unavailable_message(
    agegr1_rule: DerivationRule,
) -> None:
    # Arrange
    ctx = _make_ctx(agegr1_rule, repo=None)

    # Act
    result = await query_patterns(ctx)

    # Assert
    assert result == "No pattern history available."


async def test_query_patterns_with_empty_db_returns_no_history_message(
    pattern_repo: PatternRepository,
    agegr1_rule: DerivationRule,
) -> None:
    # Arrange
    ctx = _make_ctx(agegr1_rule, repo=pattern_repo)

    # Act
    result = await query_patterns(ctx)

    # Assert
    assert result == "No prior patterns found for this variable."


async def test_query_patterns_returns_formatted_patterns_when_found(
    pattern_repo: PatternRepository,
    agegr1_rule: DerivationRule,
) -> None:
    # Arrange
    await pattern_repo.store(
        variable_type="AGEGR1",
        spec_logic="<65 / 65-80 / >80",
        approved_code="pd.cut(df['age'], bins=[0, 65, 80, 999], labels=['<65', '65-80', '>80'])",
        study="CDISCPILOT01",
        approach="pd.cut",
    )
    await pattern_repo.store(
        variable_type="AGEGR1",
        spec_logic="<65 / 65-80 / >80",
        approved_code="np.select([df['age'] < 65, df['age'] <= 80], ['<65', '65-80'], default='>80')",
        study="CDISCPILOT01",
        approach="np.select",
    )
    ctx = _make_ctx(agegr1_rule, repo=pattern_repo)

    # Act
    result = await query_patterns(ctx)

    # Assert — both patterns appear in output
    assert "PATTERN 1" in result
    assert "PATTERN 2" in result
    assert "pd.cut" in result
    assert "np.select" in result
    assert "CDISCPILOT01" in result


async def test_query_patterns_respects_variable_type_filter(
    pattern_repo: PatternRepository,
    agegr1_rule: DerivationRule,
    trtdur_rule: DerivationRule,
) -> None:
    # Arrange — seed one AGEGR1 and one TRTDUR row
    await pattern_repo.store(
        variable_type="AGEGR1",
        spec_logic="<65 / 65-80 / >80",
        approved_code="agegr1_code()",
        study="STUDY01",
        approach="pd.cut",
    )
    await pattern_repo.store(
        variable_type="TRTDUR",
        spec_logic="Days between end and start",
        approved_code="trtdur_code()",
        study="STUDY01",
        approach="diff",
    )
    ctx = _make_ctx(agegr1_rule, repo=pattern_repo)

    # Act
    result = await query_patterns(ctx)

    # Assert — only AGEGR1 row returned, not TRTDUR
    assert "agegr1_code" in result
    assert "trtdur_code" not in result


async def test_query_patterns_caps_at_three_patterns(
    pattern_repo: PatternRepository,
    agegr1_rule: DerivationRule,
) -> None:
    # Arrange — seed 10 rows for AGEGR1
    for i in range(10):
        await pattern_repo.store(
            variable_type="AGEGR1",
            spec_logic=f"logic_{i}",
            approved_code=f"code_{i}",
            study="STUDY01",
            approach=f"approach_{i}",
        )
    ctx = _make_ctx(agegr1_rule, repo=pattern_repo)

    # Act
    result = await query_patterns(ctx)

    # Assert — exactly 3 patterns (PATTERN 1, 2, 3 — but NOT PATTERN 4)
    assert "PATTERN 1" in result
    assert "PATTERN 2" in result
    assert "PATTERN 3" in result
    assert "PATTERN 4" not in result
