"""Debugger agent — analyses QC mismatches and identifies the correct implementation."""

from __future__ import annotations

from src.agents.deps import DebuggerDeps as DebuggerDeps  # re-export
from src.agents.factory import load_agent
from src.agents.types import DebugAnalysis as DebugAnalysis  # re-export

debugger_agent = load_agent("config/agents/debugger.yaml")
