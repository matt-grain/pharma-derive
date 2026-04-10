"""Workflow state and result models — extracted from orchestrator.py for module focus."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pandas as pd  # noqa: TC002 — used in WorkflowState dataclass field at runtime
from pydantic import BaseModel

from src.domain.models import (  # noqa: TC001 — Pydantic needs these at runtime for model validation
    AuditRecord,
    AuditSummary,
    WorkflowStatus,
)

if TYPE_CHECKING:
    from src.domain.dag import DerivationDAG
    from src.domain.models import TransformationSpec


@dataclass
class WorkflowState:
    """Mutable workflow state carried across orchestration steps."""

    workflow_id: str
    spec: TransformationSpec | None = None
    dag: DerivationDAG | None = None
    derived_df: pd.DataFrame | None = None
    synthetic_csv: str = ""
    current_variable: str | None = None
    audit_summary: AuditSummary | None = None
    errors: list[str] = field(default_factory=lambda: list[str]())
    started_at: str | None = None
    completed_at: str | None = None


class WorkflowResult(BaseModel, frozen=True):
    """Immutable summary returned after a completed or failed run."""

    workflow_id: str
    study: str
    status: WorkflowStatus
    derived_variables: list[str]
    qc_summary: dict[str, str]
    audit_records: list[AuditRecord]
    audit_summary: AuditSummary | None = None
    errors: list[str]
    duration_seconds: float
