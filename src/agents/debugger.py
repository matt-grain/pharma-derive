"""Debugger agent — analyses QC mismatches and identifies the correct implementation."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from src.domain.models import DerivationRule  # noqa: TC001 — used in DebuggerDeps dataclass at runtime

_model = OpenAIChatModel(
    "cdde-agent",
    provider=OpenAIProvider(base_url="http://localhost:8650/v1", api_key="not-needed-for-mailbox"),
)


class DebugAnalysis(BaseModel, frozen=True):
    """Structured output of the debugger agent."""

    variable_name: str
    root_cause: str
    correct_implementation: str  # "coder", "qc", or "neither"
    suggested_fix: str
    confidence: str  # "high", "medium", "low"


@dataclass
class DebuggerDeps:
    """Dependencies for the debugger agent."""

    rule: DerivationRule
    coder_code: str
    qc_code: str
    divergent_summary: str
    available_columns: list[str]


debugger_agent: Agent[DebuggerDeps, DebugAnalysis] = Agent(
    _model,
    output_type=DebugAnalysis,
    deps_type=DebuggerDeps,
    retries=3,
    system_prompt=(
        "You are a senior clinical programmer debugging a QC mismatch. "
        "Analyze why two implementations of the same derivation rule "
        "produce different results. Determine which is correct and suggest a fix."
    ),
)
