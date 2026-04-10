from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002 — stored as self._session at runtime

from src.domain.models import FeedbackRecord, PatternRecord, QCStats, QCVerdict
from src.persistence.orm_models import (
    FeedbackRow,
    PatternRow,
    QCHistoryRow,
    WorkflowStateRow,
)


class PatternRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def store(
        self,
        variable_type: str,
        spec_logic: str,
        approved_code: str,
        study: str,
        approach: str,
    ) -> int:
        row = PatternRow(
            variable_type=variable_type,
            spec_logic=spec_logic,
            approved_code=approved_code,
            study=study,
            approach=approach,
            created_at=datetime.now(UTC),
        )
        self._session.add(row)
        await self._session.flush()
        return row.id  # type: ignore[return-value]

    async def query_by_type(self, variable_type: str, limit: int = 5) -> list[PatternRecord]:
        stmt = (
            select(PatternRow)
            .where(PatternRow.variable_type == variable_type)
            .order_by(PatternRow.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
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


class FeedbackRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def store(self, variable: str, feedback: str, action_taken: str, study: str) -> int:
        row = FeedbackRow(
            variable=variable,
            feedback=feedback,
            action_taken=action_taken,
            study=study,
            created_at=datetime.now(UTC),
        )
        self._session.add(row)
        await self._session.flush()
        return row.id  # type: ignore[return-value]

    async def query_by_variable(self, variable: str, limit: int = 5) -> list[FeedbackRecord]:
        stmt = (
            select(FeedbackRow)
            .where(FeedbackRow.variable == variable)
            .order_by(FeedbackRow.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
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


class QCHistoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def store(
        self,
        variable: str,
        verdict: QCVerdict,
        coder_approach: str,
        qc_approach: str,
        study: str,
    ) -> None:
        row = QCHistoryRow(
            variable=variable,
            verdict=verdict.value,
            coder_approach=coder_approach,
            qc_approach=qc_approach,
            study=study,
            created_at=datetime.now(UTC),
        )
        self._session.add(row)
        await self._session.flush()

    async def get_stats(self, variable: str | None = None) -> QCStats:
        base = select(func.count()).select_from(QCHistoryRow)
        match_stmt = select(func.count()).select_from(QCHistoryRow).where(QCHistoryRow.verdict == QCVerdict.MATCH.value)
        if variable:
            base = base.where(QCHistoryRow.variable == variable)
            match_stmt = match_stmt.where(QCHistoryRow.variable == variable)
        total_result = await self._session.execute(base)
        total = total_result.scalar() or 0
        match_result = await self._session.execute(match_stmt)
        matches = match_result.scalar() or 0
        return QCStats(
            total=total,
            matches=matches,
            mismatches=total - matches,
            match_rate=matches / total if total > 0 else 0.0,
        )


class WorkflowStateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, workflow_id: str, state_json: str, fsm_state: str) -> None:
        stmt = select(WorkflowStateRow).where(WorkflowStateRow.workflow_id == workflow_id)
        result = await self._session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            existing.state_json = state_json
            existing.fsm_state = fsm_state
            existing.updated_at = datetime.now(UTC)
        else:
            row = WorkflowStateRow(
                workflow_id=workflow_id,
                state_json=state_json,
                fsm_state=fsm_state,
                updated_at=datetime.now(UTC),
            )
            self._session.add(row)
        await self._session.flush()

    async def load(self, workflow_id: str) -> str | None:
        stmt = select(WorkflowStateRow).where(WorkflowStateRow.workflow_id == workflow_id)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return row.state_json if row else None

    async def delete(self, workflow_id: str) -> None:
        stmt = select(WorkflowStateRow).where(WorkflowStateRow.workflow_id == workflow_id)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row:
            await self._session.delete(row)
            await self._session.flush()
