"""Integration test: all three LTM tools return data after seeded run.

Proves the full LTM read loop (query_patterns + query_feedback + query_qc_history)
can be invoked after seeding all three tables — no LLM calls required.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pandas as pd
from pydantic_ai import RunContext

from src.agents.deps import CoderDeps
from src.agents.tools.query_feedback import query_feedback
from src.agents.tools.query_patterns import query_patterns
from src.agents.tools.query_qc_history import query_qc_history
from src.domain.models import DerivationRule, OutputDType, QCVerdict
from src.persistence.database import init_db
from src.persistence.feedback_repo import FeedbackRepository
from src.persistence.pattern_repo import PatternRepository
from src.persistence.qc_history_repo import QCHistoryRepository

if TYPE_CHECKING:
    from pathlib import Path


def _make_ctx(
    rule: DerivationRule,
    pattern_repo: PatternRepository,
    feedback_repo: FeedbackRepository,
    qc_history_repo: QCHistoryRepository,
) -> RunContext[CoderDeps]:
    """Build a RunContext stub wired with all three LTM repositories."""
    deps = CoderDeps(
        df=pd.DataFrame({"age": [72, 45]}),
        synthetic_csv="age\n72\n45",
        rule=rule,
        available_columns=["age"],
        pattern_repo=pattern_repo,
        feedback_repo=feedback_repo,
        qc_history_repo=qc_history_repo,
    )
    ctx: RunContext[CoderDeps] = MagicMock(spec=RunContext)
    ctx.deps = deps
    return ctx


async def test_three_tools_return_data_after_seeded_run(tmp_path: Path) -> None:
    """All three LTM tools return non-empty data after directly seeding all three tables."""
    # Arrange — shared in-memory SQLite with all tables
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'ltm_three_tools.db'}"
    session_factory = await init_db(db_url)

    variable = "AGE_GROUP"
    rule = DerivationRule(
        variable=variable,
        source_columns=["age"],
        logic="<65 / 65-80 / >80",
        output_type=OutputDType.STR,
    )

    async with session_factory() as session:
        pat_repo = PatternRepository(session)
        fb_repo = FeedbackRepository(session)
        qc_repo = QCHistoryRepository(session)

        # Seed patterns table
        await pat_repo.store(
            variable_type=variable,
            spec_logic="<65 / 65-80 / >80",
            approved_code="pd.cut(df['age'], bins=[0,65,80,999], labels=['<65','65-80','>80'])",
            study="CDISCPILOT01",
            approach="pd.cut",
        )

        # Seed feedback table
        await fb_repo.store(
            variable=variable,
            feedback="Reviewer prefers np.select over pd.cut for clarity",
            action_taken="overridden",
            study="CDISCPILOT01",
        )

        # Seed qc_history table
        await qc_repo.store(
            variable=variable,
            verdict=QCVerdict.MISMATCH,
            coder_approach="pd.cut",
            qc_approach="np.select",
            study="CDISCPILOT01",
        )

        ctx = _make_ctx(rule, pat_repo, fb_repo, qc_repo)

        # Act — call all three tools against the seeded session
        patterns_result = await query_patterns(ctx)
        feedback_result = await query_feedback(ctx)
        qc_result = await query_qc_history(ctx)

    # Assert — each tool returns non-empty string with the seeded data marker
    assert "PATTERN" in patterns_result, f"Expected PATTERN in patterns result, got: {patterns_result!r}"
    assert "FEEDBACK" in feedback_result, f"Expected FEEDBACK in feedback result, got: {feedback_result!r}"
    assert "QC HISTORY" in qc_result, f"Expected QC HISTORY in qc result, got: {qc_result!r}"

    # Assert — seeded content is visible in each result
    assert "pd.cut" in patterns_result
    assert "np.select" in feedback_result
    assert "mismatch" in qc_result
