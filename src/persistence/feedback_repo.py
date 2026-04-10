"""FeedbackRepository — stores and queries human feedback on derivations."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from src.domain.models import FeedbackRecord
from src.persistence.base_repo import BaseRepository
from src.persistence.orm_models import FeedbackRow


class FeedbackRepository(BaseRepository):
    """Stores human feedback for learning across runs."""

    async def store(self, variable: str, feedback: str, action_taken: str, study: str) -> int:
        """Persist human feedback to improve future derivation attempts."""
        row = FeedbackRow(
            variable=variable,
            feedback=feedback,
            action_taken=action_taken,
            study=study,
            created_at=datetime.now(UTC),
        )
        self._session.add(row)
        await self._flush()
        return row.id  # type: ignore[return-value]

    async def query_by_variable(self, variable: str, limit: int = 5) -> list[FeedbackRecord]:
        """Retrieve recent feedback for a variable to inform retry strategy."""
        stmt = (
            select(FeedbackRow)
            .where(FeedbackRow.variable == variable)
            .order_by(FeedbackRow.created_at.desc())
            .limit(limit)
        )
        result = await self._execute(stmt)
        return [
            FeedbackRecord(
                id=row.id,
                variable=row.variable,
                feedback=row.feedback,
                action_taken=row.action_taken,
                study=row.study,
                created_at=row.created_at.isoformat(),
            )
            for row in result.scalars()
        ]
