"""WorkflowStateRepository — persists and loads workflow FSM state."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from src.persistence.base_repo import BaseRepository
from src.persistence.orm_models import WorkflowStateRow


class WorkflowStateRepository(BaseRepository):
    """Persists workflow FSM state for crash recovery and audit."""

    async def save(self, workflow_id: str, state_json: str, fsm_state: str) -> None:
        """Persist or update workflow state for crash recovery."""
        stmt = select(WorkflowStateRow).where(WorkflowStateRow.workflow_id == workflow_id)
        result = await self._execute(stmt)
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
        await self._flush()

    async def load(self, workflow_id: str) -> str | None:
        """Load serialized workflow state, or None if not found."""
        stmt = select(WorkflowStateRow).where(WorkflowStateRow.workflow_id == workflow_id)
        result = await self._execute(stmt)
        row = result.scalar_one_or_none()
        return row.state_json if row else None

    async def delete(self, workflow_id: str) -> None:
        """Remove workflow state after successful completion."""
        stmt = select(WorkflowStateRow).where(WorkflowStateRow.workflow_id == workflow_id)
        result = await self._execute(stmt)
        row = result.scalar_one_or_none()
        if row:
            await self._session.delete(row)
            await self._flush()
