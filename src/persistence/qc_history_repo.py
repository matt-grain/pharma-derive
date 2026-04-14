"""QCHistoryRepository — stores and aggregates QC verdict history."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select

from src.domain.models import QCHistoryRecord, QCStats, QCVerdict
from src.persistence.base_repo import BaseRepository
from src.persistence.orm_models import QCHistoryRow


class QCHistoryRepository(BaseRepository):
    """Stores QC verdict history and provides aggregate statistics."""

    async def store(
        self,
        variable: str,
        verdict: QCVerdict,
        coder_approach: str,
        qc_approach: str,
        study: str,
    ) -> None:
        """Append a QC verdict record for trend analysis across runs."""
        row = QCHistoryRow(
            variable=variable,
            verdict=verdict.value,
            coder_approach=coder_approach,
            qc_approach=qc_approach,
            study=study,
            created_at=datetime.now(UTC),
        )
        self._session.add(row)
        await self._flush()

    async def query_by_variable(self, variable: str, limit: int = 5) -> list[QCHistoryRecord]:
        """Retrieve recent QC verdict rows for a variable, ordered most-recent first."""
        stmt = (
            select(QCHistoryRow)
            .where(QCHistoryRow.variable == variable)
            .order_by(QCHistoryRow.created_at.desc())
            .limit(limit)
        )
        result = await self._execute(stmt)
        return [
            QCHistoryRecord(
                id=row.id,
                variable=row.variable,
                verdict=row.verdict,
                coder_approach=row.coder_approach,
                qc_approach=row.qc_approach,
                study=row.study,
                created_at=row.created_at.isoformat(),
            )
            for row in result.scalars()
        ]

    async def get_stats(self, variable: str | None = None) -> QCStats:
        """Compute aggregate QC match/mismatch statistics."""
        base = select(func.count()).select_from(QCHistoryRow)
        match_stmt = select(func.count()).select_from(QCHistoryRow).where(QCHistoryRow.verdict == QCVerdict.MATCH.value)
        if variable:
            base = base.where(QCHistoryRow.variable == variable)
            match_stmt = match_stmt.where(QCHistoryRow.variable == variable)
        total_result = await self._execute(base)
        total: int = total_result.scalar() or 0  # Any: SQLAlchemy scalar() returns untyped result
        match_result = await self._execute(match_stmt)
        matches: int = match_result.scalar() or 0  # Any: SQLAlchemy scalar() returns untyped result
        return QCStats(
            total=total,
            matches=matches,
            mismatches=total - matches,
            match_rate=matches / total if total > 0 else 0.0,
        )
