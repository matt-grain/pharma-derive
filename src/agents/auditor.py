"""Auditor agent — generates regulatory compliance summary for the audit trail."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai import Agent

from src.domain.models import AuditSummary, SpecMetadata


@dataclass
class AuditorDeps:
    """Dependencies for the auditor agent."""

    dag_summary: str
    workflow_id: str
    spec_metadata: SpecMetadata


auditor_agent: Agent[AuditorDeps, AuditSummary] = Agent(
    "test",  # overridden at call time via model= parameter
    output_type=AuditSummary,
    deps_type=AuditorDeps,
    retries=3,
    system_prompt=(
        "You are a regulatory compliance auditor reviewing a clinical data "
        "derivation workflow. Summarize the derivation process, flag concerns, "
        "and provide recommendations for the audit trail."
    ),
)
