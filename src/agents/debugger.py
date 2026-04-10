"""Debugger agent — analyses QC mismatches and identifies the correct implementation."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel
from pydantic_ai import Agent

from src.domain.models import (  # noqa: TC001 — used in DebuggerDeps dataclass at runtime
    ConfidenceLevel,
    CorrectImplementation,
    DerivationRule,
)


class DebugAnalysis(BaseModel, frozen=True):
    """Structured output of the debugger agent."""

    variable_name: str
    root_cause: str
    correct_implementation: CorrectImplementation
    suggested_fix: str
    confidence: ConfidenceLevel


@dataclass
class DebuggerDeps:
    """Dependencies for the debugger agent."""

    rule: DerivationRule
    coder_code: str
    qc_code: str
    divergent_summary: str
    available_columns: list[str]


debugger_agent: Agent[DebuggerDeps, DebugAnalysis] = Agent(
    "test",  # overridden at call time via model= parameter
    name="debugger",
    output_type=DebugAnalysis,
    deps_type=DebuggerDeps,
    retries=3,
    system_prompt=(
        "You are a senior clinical programmer debugging a QC mismatch. "
        "Analyze why two implementations of the same derivation rule "
        "produce different results. Determine which is correct and suggest a fix."
    ),
)
