"""Auditor agent — generates regulatory compliance summary for the audit trail."""

from __future__ import annotations

from src.agents.deps import AuditorDeps as AuditorDeps  # re-export for backward compat
from src.agents.factory import load_agent

auditor_agent = load_agent("config/agents/auditor.yaml")
