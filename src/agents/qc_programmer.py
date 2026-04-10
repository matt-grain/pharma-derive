"""QC programmer agent — independent verification using an alternative approach."""

from __future__ import annotations

from src.agents.factory import load_agent

qc_agent = load_agent("config/agents/qc_programmer.yaml")
