"""Agent output types — Pydantic models for structured agent responses.

Extracted to a leaf module to avoid circular imports with the agent factory.
"""

from __future__ import annotations

from pydantic import BaseModel

from src.domain.models import (  # noqa: TC001 — used at runtime by Pydantic
    ConfidenceLevel,
    CorrectImplementation,
    DerivationRule,
)


class DerivationCode(BaseModel, frozen=True):
    """Structured output of the derivation coder and QC programmer agents."""

    variable_name: str
    python_code: str
    approach: str
    null_handling: str


class DebugAnalysis(BaseModel, frozen=True):
    """Structured output of the debugger agent."""

    variable_name: str
    root_cause: str
    correct_implementation: CorrectImplementation
    suggested_fix: str
    confidence: ConfidenceLevel


class SpecInterpretation(BaseModel, frozen=True):
    """Structured output of the spec interpreter agent."""

    rules: list[DerivationRule]
    ambiguities: list[str]
    summary: str
