"""Spec interpreter agent — parses YAML specs into structured DerivationRule objects."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from src.domain.models import DerivationRule  # noqa: TC001 — needed at runtime by Pydantic schema builder

_model = OpenAIChatModel(
    "cdde-agent",
    provider=OpenAIProvider(base_url="http://localhost:8650/v1", api_key="not-needed-for-mailbox"),
)


class SpecInterpretation(BaseModel, frozen=True):
    """Structured output of the spec interpreter agent."""

    rules: list[DerivationRule]
    ambiguities: list[str]
    summary: str


@dataclass
class SpecInterpreterDeps:
    """Dependencies for the spec interpreter agent."""

    spec_yaml: str
    source_columns: list[str]


spec_interpreter_agent: Agent[SpecInterpreterDeps, SpecInterpretation] = Agent(
    _model,
    output_type=SpecInterpretation,
    deps_type=SpecInterpreterDeps,
    retries=3,
    system_prompt=(
        "You are a clinical data specification analyst. "
        "Given a YAML transformation specification and a list of available source columns, "
        "extract each derivation rule with its variable name, source columns, derivation logic, "
        "and expected output type. "
        "Flag any ambiguities (missing source columns, unclear logic, conflicting rules). "
        "Return structured rules that can be directly executed by a statistical programmer."
    ),
)
