"""Domain models for YAML-driven pipeline configuration."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from pathlib import Path


class StepType(StrEnum):
    """Composition type for a pipeline step."""

    AGENT = "agent"
    BUILTIN = "builtin"
    GATHER = "gather"
    PARALLEL_MAP = "parallel_map"
    HITL_GATE = "hitl_gate"


class StepDefinition(BaseModel, frozen=True):
    """A single step in a pipeline configuration."""

    id: str
    type: StepType
    description: str = ""
    agent: str | None = None  # agent YAML name, for type=agent
    agents: list[str] | None = None  # multiple agents, for type=gather
    builtin: str | None = None  # builtin function name, for type=builtin
    depends_on: list[str] = []
    config: dict[str, str | int | float | bool | list[str]] = {}
    sub_steps: list[StepDefinition] | None = None  # for type=parallel_map
    condition: str | None = None  # e.g. "verdict == 'mismatch'"
    over: str | None = None  # iteration target for parallel_map, e.g. "dag_layers"


# Self-referential model — must be rebuilt after class definition (Pydantic v2 requirement)
StepDefinition.model_rebuild()


class PipelineDefinition(BaseModel, frozen=True):
    """Top-level pipeline configuration parsed from YAML."""

    name: str
    version: str = "1.0"
    description: str = ""
    steps: list[StepDefinition]


def load_pipeline(yaml_path: str | Path) -> PipelineDefinition:
    """Parse a pipeline YAML file into a PipelineDefinition."""
    from pathlib import Path

    import yaml

    path = Path(yaml_path)
    if not path.exists():
        msg = f"Pipeline config not found: {path}"
        raise FileNotFoundError(msg)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    pipeline_data = raw.get("pipeline", raw)  # support both root-level and nested
    return PipelineDefinition.model_validate(pipeline_data)
