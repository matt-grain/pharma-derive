"""Unit tests for the persistence layer (repositories + DB init).

All tests use an in-memory SQLite database for isolation.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator  # noqa: TC003 — used at runtime in pytest fixture return type

import pytest
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002 — used at runtime in pytest fixture return type

from src.domain.models import QCVerdict
from src.persistence.database import init_db
from src.persistence.repositories import (
    FeedbackRepository,
    PatternRepository,
    QCHistoryRepository,
    WorkflowStateRepository,
)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession]:
    session_factory = await init_db("sqlite+aiosqlite:///:memory:")
    async with session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# PatternRepository
# ---------------------------------------------------------------------------


async def test_pattern_repo_store_and_query(db_session: AsyncSession) -> None:
    # Arrange
    repo = PatternRepository(db_session)

    # Act
    stored_id = await repo.store(
        variable_type="age_group",
        spec_logic="If age < 18 → minor",
        approved_code="df['age'].apply(lambda x: 'minor' if x < 18 else 'adult')",
        study="CDISCPILOT01",
        approach="pandas apply with lambda",
    )
    records = await repo.query_by_type("age_group")

    # Assert
    assert stored_id >= 1
    assert len(records) == 1
    assert records[0].variable_type == "age_group"
    assert records[0].spec_logic == "If age < 18 → minor"
    assert records[0].study == "CDISCPILOT01"
    assert records[0].approach == "pandas apply with lambda"
    assert "T" in records[0].created_at  # ISO 8601 format


async def test_pattern_repo_query_empty_returns_empty_list(db_session: AsyncSession) -> None:
    # Arrange
    repo = PatternRepository(db_session)

    # Act
    records = await repo.query_by_type("nonexistent_type")

    # Assert
    assert records == []


async def test_pattern_repo_query_respects_limit(db_session: AsyncSession) -> None:
    # Arrange
    repo = PatternRepository(db_session)
    for i in range(10):
        await repo.store(
            variable_type="age_group",
            spec_logic=f"logic_{i}",
            approved_code=f"code_{i}",
            study="STUDY01",
            approach=f"approach_{i}",
        )

    # Act
    records = await repo.query_by_type("age_group", limit=3)

    # Assert
    assert len(records) == 3


# ---------------------------------------------------------------------------
# FeedbackRepository
# ---------------------------------------------------------------------------


async def test_feedback_repo_store_and_query(db_session: AsyncSession) -> None:
    # Arrange
    repo = FeedbackRepository(db_session)

    # Act
    stored_id = await repo.store(
        variable="AGE_GROUP",
        feedback="Output looks correct but consider edge case for age=65",
        action_taken="accepted_with_note",
        study="CDISCPILOT01",
    )
    records = await repo.query_by_variable("AGE_GROUP")

    # Assert
    assert stored_id >= 1
    assert len(records) == 1
    assert records[0].variable == "AGE_GROUP"
    assert records[0].action_taken == "accepted_with_note"
    assert records[0].study == "CDISCPILOT01"
    assert "T" in records[0].created_at


# ---------------------------------------------------------------------------
# QCHistoryRepository
# ---------------------------------------------------------------------------


async def test_qc_repo_store_and_get_stats(db_session: AsyncSession) -> None:
    # Arrange
    repo = QCHistoryRepository(db_session)
    await repo.store("AGE_GROUP", QCVerdict.MATCH, "pandas apply", "numpy where", "STUDY01")
    await repo.store("AGE_GROUP", QCVerdict.MATCH, "pandas apply", "numpy select", "STUDY01")
    await repo.store("AGE_GROUP", QCVerdict.MISMATCH, "pandas map", "numpy where", "STUDY01")

    # Act
    stats = await repo.get_stats()

    # Assert
    assert stats.total == 3
    assert stats.matches == 2
    assert stats.mismatches == 1
    assert abs(stats.match_rate - 2 / 3) < 1e-6


async def test_qc_repo_stats_empty(db_session: AsyncSession) -> None:
    # Arrange
    repo = QCHistoryRepository(db_session)

    # Act
    stats = await repo.get_stats()

    # Assert
    assert stats.total == 0
    assert stats.match_rate == 0.0
    assert stats.mismatches == 0


# ---------------------------------------------------------------------------
# WorkflowStateRepository
# ---------------------------------------------------------------------------


async def test_workflow_state_repo_save_and_load(db_session: AsyncSession) -> None:
    # Arrange
    repo = WorkflowStateRepository(db_session)
    workflow_id = "wf_abc123"
    state_json = '{"step": "deriving", "variable": "AGE_GROUP"}'

    # Act
    await repo.save(workflow_id, state_json, "deriving")
    loaded = await repo.load(workflow_id)

    # Assert
    assert loaded == state_json


async def test_workflow_state_repo_save_updates_existing(db_session: AsyncSession) -> None:
    # Arrange
    repo = WorkflowStateRepository(db_session)
    workflow_id = "wf_update01"

    # Act — save once, then overwrite
    await repo.save(workflow_id, '{"step": "deriving"}', "deriving")
    await repo.save(workflow_id, '{"step": "completed"}', "completed")
    loaded = await repo.load(workflow_id)

    # Assert — second save wins
    assert loaded == '{"step": "completed"}'


async def test_workflow_state_repo_load_nonexistent_returns_none(db_session: AsyncSession) -> None:
    # Arrange
    repo = WorkflowStateRepository(db_session)

    # Act
    result = await repo.load("nonexistent_workflow")

    # Assert
    assert result is None


async def test_workflow_state_repo_delete(db_session: AsyncSession) -> None:
    # Arrange
    repo = WorkflowStateRepository(db_session)
    workflow_id = "wf_delete01"
    await repo.save(workflow_id, '{"step": "completed"}', "completed")

    # Act
    await repo.delete(workflow_id)
    result = await repo.load(workflow_id)

    # Assert
    assert result is None


# ---------------------------------------------------------------------------
# DB initialisation
# ---------------------------------------------------------------------------


async def test_init_db_creates_tables() -> None:
    # Arrange & Act
    session_factory = await init_db("sqlite+aiosqlite:///:memory:")

    # Assert — we can open a session and execute without error
    async with session_factory() as session:
        from sqlalchemy import text

        result = await session.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        table_names = {row[0] for row in result}

    assert "patterns" in table_names
    assert "feedback" in table_names
    assert "qc_history" in table_names
    assert "workflow_states" in table_names


# ---------------------------------------------------------------------------
# FeedbackRepository — edge cases
# ---------------------------------------------------------------------------


async def test_feedback_repo_query_empty_returns_empty_list(db_session: AsyncSession) -> None:
    """Querying feedback with no records returns empty list."""
    # Arrange
    repo = FeedbackRepository(db_session)

    # Act
    results = await repo.query_by_variable("NONEXISTENT")

    # Assert
    assert results == []


async def test_feedback_repo_query_respects_limit(db_session: AsyncSession) -> None:
    """Querying feedback respects the limit parameter."""
    # Arrange
    repo = FeedbackRepository(db_session)
    for i in range(5):
        await repo.store(variable="AGE", feedback=f"feedback {i}", action_taken="fixed", study="test")

    # Act
    results = await repo.query_by_variable("AGE", limit=2)

    # Assert
    assert len(results) == 2


# ---------------------------------------------------------------------------
# QCHistoryRepository — edge cases
# ---------------------------------------------------------------------------


async def test_qc_repo_stats_filtered_by_variable(db_session: AsyncSession) -> None:
    """QC stats filtered by variable only count matching records."""
    # Arrange
    repo = QCHistoryRepository(db_session)
    await repo.store(
        variable="AGE_GROUP", verdict=QCVerdict.MATCH, coder_approach="cut", qc_approach="select", study="test"
    )
    await repo.store(
        variable="AGE_GROUP", verdict=QCVerdict.MISMATCH, coder_approach="cut", qc_approach="where", study="test"
    )
    await repo.store(variable="TRTDUR", verdict=QCVerdict.MATCH, coder_approach="diff", qc_approach="sub", study="test")

    # Act
    stats = await repo.get_stats(variable="AGE_GROUP")

    # Assert
    assert stats.total == 2
    assert stats.matches == 1
    assert stats.mismatches == 1
