"""Shared dependency containers for all agents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pandas as pd  # noqa: TC002 — used at runtime in dataclass field

if TYPE_CHECKING:
    from src.domain.models import DerivationRule, SpecMetadata
    from src.persistence.feedback_repo import FeedbackRepository
    from src.persistence.pattern_repo import PatternRepository
    from src.persistence.qc_history_repo import QCHistoryRepository


@dataclass
class CoderDeps:
    """Dependencies injected into Coder and QC agents."""

    df: pd.DataFrame
    synthetic_csv: str
    rule: DerivationRule
    available_columns: list[str]
    pattern_repo: PatternRepository | None = None
    feedback_repo: FeedbackRepository | None = None
    qc_history_repo: QCHistoryRepository | None = None


@dataclass
class AuditorDeps:
    """Dependencies for the auditor agent."""

    dag_summary: str
    workflow_id: str
    spec_metadata: SpecMetadata


@dataclass
class DebuggerDeps:
    """Dependencies for the debugger agent."""

    rule: DerivationRule
    coder_code: str
    qc_code: str
    divergent_summary: str
    available_columns: list[str]


@dataclass
class SpecInterpreterDeps:
    """Dependencies for the spec interpreter agent."""

    spec_yaml: str
    source_columns: list[str]
