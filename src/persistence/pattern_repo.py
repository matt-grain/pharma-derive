"""PatternRepository — stores and queries approved derivation patterns."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from src.domain.models import PatternRecord
from src.persistence.base_repo import BaseRepository
from src.persistence.orm_models import PatternRow


class PatternRepository(BaseRepository):
    """Stores approved derivation patterns for cross-run reuse."""

    async def store(
        self,
        variable_type: str,
        spec_logic: str,
        approved_code: str,
        study: str,
        approach: str,
    ) -> int:
        """Persist a validated pattern for cross-run reuse."""
        row = PatternRow(
            variable_type=variable_type,
            spec_logic=spec_logic,
            approved_code=approved_code,
            study=study,
            approach=approach,
            created_at=datetime.now(UTC),
        )
        self._session.add(row)
        await self._flush()
        return row.id  # type: ignore[return-value]

    async def query_by_type(self, variable_type: str, limit: int = 5) -> list[PatternRecord]:
        """Retrieve recent patterns matching a variable type for prompt seeding."""
        stmt = (
            select(PatternRow)
            .where(PatternRow.variable_type == variable_type)
            .order_by(PatternRow.created_at.desc())
            .limit(limit)
        )
        result = await self._execute(stmt)
        return [
            PatternRecord(
                id=row.id,
                variable_type=row.variable_type,
                spec_logic=row.spec_logic,
                approved_code=row.approved_code,
                study=row.study,
                approach=row.approach,
                created_at=row.created_at.isoformat(),
            )
            for row in result.scalars()
        ]
