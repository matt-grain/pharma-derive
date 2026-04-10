"""Spec interpreter agent — parses YAML specs into structured DerivationRule objects."""

from __future__ import annotations

from src.agents.deps import SpecInterpreterDeps as SpecInterpreterDeps  # re-export
from src.agents.factory import load_agent
from src.agents.types import SpecInterpretation as SpecInterpretation  # re-export

spec_interpreter_agent = load_agent("config/agents/spec_interpreter.yaml")
