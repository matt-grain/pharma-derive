"""Agent registries — maps YAML string names to Python types and tool functions."""

from __future__ import annotations

from typing import Any  # Any: heterogeneous type registry mapping strings to various Pydantic/dataclass types

from src.agents.deps import AuditorDeps, CoderDeps, DebuggerDeps, SpecInterpreterDeps
from src.agents.tools import execute_code, inspect_data
from src.agents.types import DebugAnalysis, DerivationCode, SpecInterpretation
from src.domain.models import AuditSummary

OUTPUT_TYPE_MAP: dict[str, type[Any]] = {
    "DerivationCode": DerivationCode,
    "DebugAnalysis": DebugAnalysis,
    "AuditSummary": AuditSummary,
    "SpecInterpretation": SpecInterpretation,
}

DEPS_TYPE_MAP: dict[str, type[Any]] = {
    "CoderDeps": CoderDeps,
    "DebuggerDeps": DebuggerDeps,
    "AuditorDeps": AuditorDeps,
    "SpecInterpreterDeps": SpecInterpreterDeps,
}

TOOL_MAP: dict[str, Any] = {  # Any: PydanticAI tool signatures vary
    "inspect_data": inspect_data,
    "execute_code": execute_code,
}
