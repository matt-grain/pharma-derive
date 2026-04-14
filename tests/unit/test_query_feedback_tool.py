"""Unit tests for the query_feedback tool.

Tests cover: no repo, empty DB, results returned, variable filter, and 3-record cap.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pandas as pd
import pytest
from pydantic_ai import RunContext

from src.agents.deps import CoderDeps
from src.agents.tools.query_feedback import query_feedback
from src.domain.models import DerivationRule, OutputDType
from src.persistence.database import init_db
from src.persistence.feedback_repo import FeedbackRepository

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@pytest.fixture
async def feedback_repo() -> AsyncGenerator[FeedbackRepository]:
    session_factory = await init_db("sqlite+aiosqlite:///:memory:")
    async with session_factory() as session:
        yield FeedbackRepository(session)


def _make_ctx(rule: DerivationRule, repo: FeedbackRepository | None) -> RunContext[CoderDeps]:
    """Build a minimal RunContext stub with the given FeedbackRepository."""
    deps = CoderDeps(
        df=pd.DataFrame({"age": [72, 45]}),
        synthetic_csv="age\n72\n45",
        rule=rule,
        available_columns=["age"],
        feedback_repo=repo,
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


async def test_query_feedback_with_no_repo_returns_unavailable_message(
    agegr1_rule: DerivationRule,
) -> None:
    # Arrange
    ctx = _make_ctx(agegr1_rule, repo=None)

    # Act
    result = await query_feedback(ctx)

    # Assert
    assert result == "No feedback history available."


async def test_query_feedback_with_empty_db_returns_no_history_message(
    feedback_repo: FeedbackRepository,
    agegr1_rule: DerivationRule,
) -> None:
    # Arrange
    ctx = _make_ctx(agegr1_rule, repo=feedback_repo)

    # Act
    result = await query_feedback(ctx)

    # Assert
    assert result == "No prior feedback found for this variable."


async def test_query_feedback_returns_formatted_rows_when_found(
    feedback_repo: FeedbackRepository,
    agegr1_rule: DerivationRule,
) -> None:
    # Arrange
    await feedback_repo.store(variable="AGEGR1", feedback="Great approach", action_taken="approved", study="STUDY01")
    await feedback_repo.store(
        variable="AGEGR1", feedback="Wrong bucket logic", action_taken="rejected", study="STUDY01"
    )
    await feedback_repo.store(
        variable="AGEGR1", feedback="Used np.select instead", action_taken="overridden", study="STUDY01"
    )
    ctx = _make_ctx(agegr1_rule, repo=feedback_repo)

    # Act
    result = await query_feedback(ctx)

    # Assert — all 3 records formatted with correct headers and action phrases
    assert "FEEDBACK 1" in result
    assert "FEEDBACK 2" in result
    assert "FEEDBACK 3" in result
    assert "The human reviewer approved this approach. Repeating it is safe." in result
    assert "The human reviewer rejected the previous coder's approach. Avoid generating similar code." in result
    assert "The human reviewer replaced the coder's code" in result
    assert "Great approach" in result
    assert "Wrong bucket logic" in result
    assert "Used np.select instead" in result


async def test_query_feedback_respects_variable_filter(
    feedback_repo: FeedbackRepository,
    agegr1_rule: DerivationRule,
    trtdur_rule: DerivationRule,
) -> None:
    # Arrange — seed AGEGR1 and TRTDUR rows
    await feedback_repo.store(variable="AGEGR1", feedback="agegr1 feedback", action_taken="approved", study="STUDY01")
    await feedback_repo.store(variable="TRTDUR", feedback="trtdur feedback", action_taken="rejected", study="STUDY01")
    ctx = _make_ctx(agegr1_rule, repo=feedback_repo)

    # Act
    result = await query_feedback(ctx)

    # Assert — only AGEGR1 row returned, not TRTDUR
    assert "agegr1 feedback" in result
    assert "trtdur feedback" not in result


async def test_query_feedback_caps_at_three_rows(
    feedback_repo: FeedbackRepository,
    agegr1_rule: DerivationRule,
) -> None:
    # Arrange — seed 10 rows for AGEGR1
    for i in range(10):
        await feedback_repo.store(
            variable="AGEGR1",
            feedback=f"feedback_{i}",
            action_taken="approved",
            study="STUDY01",
        )
    ctx = _make_ctx(agegr1_rule, repo=feedback_repo)

    # Act
    result = await query_feedback(ctx)

    # Assert — exactly 3 records (FEEDBACK 1, 2, 3 — but NOT FEEDBACK 4)
    assert "FEEDBACK 1" in result
    assert "FEEDBACK 2" in result
    assert "FEEDBACK 3" in result
    assert "FEEDBACK 4" not in result
