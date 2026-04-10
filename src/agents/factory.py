"""Agent factory — creates PydanticAI agents from YAML config files."""

from __future__ import annotations

from pathlib import Path
from typing import Any  # Any: factory creates agents with runtime-determined type params

import yaml
from pydantic_ai import Agent

from src.agents.registry import DEPS_TYPE_MAP, OUTPUT_TYPE_MAP, TOOL_MAP


def load_agent(yaml_path: str | Path) -> Agent[Any, Any]:
    """Load a PydanticAI agent from a YAML configuration file."""
    path = Path(yaml_path)
    if not path.exists():
        msg = f"Agent config not found: {path}"
        raise FileNotFoundError(msg)

    config = yaml.safe_load(path.read_text(encoding="utf-8"))

    name: str = config["name"]
    output_type = OUTPUT_TYPE_MAP[config["output_type"]]
    deps_type = DEPS_TYPE_MAP[config["deps_type"]]
    retries: int = config.get("retries", 3)
    system_prompt: str = config["system_prompt"].strip()
    tool_names: list[str] = config.get("tools", [])

    agent: Agent[Any, Any] = Agent(
        "test",  # overridden at call time via model= parameter
        name=name,
        output_type=output_type,
        deps_type=deps_type,
        retries=retries,
        system_prompt=system_prompt,
    )

    for tool_name in tool_names:
        if tool_name not in TOOL_MAP:
            msg = f"Unknown tool '{tool_name}' in agent config '{path.name}'. Available: {list(TOOL_MAP.keys())}"
            raise KeyError(msg)
        agent.tool(TOOL_MAP[tool_name])

    return agent
