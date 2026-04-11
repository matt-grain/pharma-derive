from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path  # noqa: TC003 — used at runtime in to_json() body (path.parent.mkdir)

from src.domain.models import AgentName, AuditAction, AuditRecord


class AuditTrail:
    """Append-only audit trail for a workflow run."""

    def __init__(self, workflow_id: str) -> None:
        self._workflow_id = workflow_id
        self._records: list[AuditRecord] = []

    @property
    def records(self) -> list[AuditRecord]:
        return list(self._records)

    def record(
        self,
        variable: str,
        action: AuditAction | str,
        agent: AgentName | str,
        details: dict[str, str | int | float | bool | None] | None = None,
    ) -> AuditRecord:
        rec = AuditRecord(
            timestamp=datetime.now(UTC).isoformat(),
            workflow_id=self._workflow_id,
            variable=variable,
            action=action,
            agent=agent,
            details=details or {},
        )
        self._records.append(rec)
        return rec

    def get_variable_history(self, variable: str) -> list[AuditRecord]:
        return [r for r in self._records if r.variable == variable]

    def to_dict(self) -> list[dict[str, object]]:
        return [r.model_dump() for r in self._records]

    def to_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, default=str))

    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self._records:
            key = f"{r.agent}:{r.action}"
            counts[key] = counts.get(key, 0) + 1
        return counts
