"""Derivation coder agent — generates primary pandas implementation for each variable."""

from __future__ import annotations

from src.agents.factory import load_agent
from src.agents.types import DerivationCode as DerivationCode  # re-export for backward compat

coder_agent = load_agent("config/agents/coder.yaml")
