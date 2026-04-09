"""Auditor agent — generates regulatory compliance summary for the audit trail."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from src.domain.models import SpecMetadata  # noqa: TC001 — used in AuditorDeps dataclass at runtime

_model = OpenAIChatModel(
    "cdde-agent",
    provider=OpenAIProvider(base_url="http://localhost:8650/v1", api_key="not-needed-for-mailbox"),
)


class AuditSummary(BaseModel, frozen=True):
    """Structured output of the auditor agent."""

    study: str
    total_derivations: int
    auto_approved: int
    qc_mismatches: int
    human_interventions: int
    summary: str
    recommendations: list[str]


@dataclass
class AuditorDeps:
    """Dependencies for the auditor agent."""

    dag_summary: str
    workflow_id: str
    spec_metadata: SpecMetadata


auditor_agent: Agent[AuditorDeps, AuditSummary] = Agent(
    _model,
    output_type=AuditSummary,
    deps_type=AuditorDeps,
    retries=3,
    system_prompt=(
        "You are a regulatory compliance auditor reviewing a clinical data "
        "derivation workflow. Summarize the derivation process, flag concerns, "
        "and provide recommendations for the audit trail."
    ),
)
