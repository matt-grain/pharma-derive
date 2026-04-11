"""Tests for the YAML agent factory and registries."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from src.agents.factory import load_agent
from src.agents.types import DerivationCode
from tests.unit.conftest import get_tool_names


def test_load_agent_creates_agent_with_correct_name() -> None:
    """Factory creates an agent with the name from YAML."""
    # Arrange & Act
    agent = load_agent("config/agents/coder.yaml")
    # Assert
    assert agent.name == "coder"


def test_load_agent_creates_agent_with_correct_output_type() -> None:
    """Factory resolves output_type from registry."""
    # Arrange & Act
    agent = load_agent("config/agents/coder.yaml")
    # Assert
    assert agent.output_type is DerivationCode


def test_load_agent_registers_tools() -> None:
    """Factory registers tools listed in YAML."""
    # Arrange & Act
    agent = load_agent("config/agents/coder.yaml")
    tool_names = get_tool_names(agent)
    # Assert
    assert "inspect_data" in tool_names
    assert "execute_code" in tool_names


def test_load_agent_no_tools_for_debugger() -> None:
    """Agents with empty tools list have no registered tools."""
    # Arrange & Act
    agent = load_agent("config/agents/debugger.yaml")
    # Assert
    assert len(get_tool_names(agent)) == 0


def test_load_agent_nonexistent_file_raises() -> None:
    """Factory raises FileNotFoundError for missing YAML."""
    # Act & Assert
    with pytest.raises(FileNotFoundError, match="Agent config not found"):
        load_agent("config/agents/nonexistent.yaml")


def test_load_agent_unknown_output_type_raises(tmp_path: Path) -> None:
    """Factory raises KeyError for unregistered output_type."""
    # Arrange
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("name: bad\noutput_type: NonExistent\ndeps_type: CoderDeps\nretries: 1\nsystem_prompt: test\n")
    # Act & Assert
    with pytest.raises(KeyError, match="NonExistent"):
        load_agent(str(bad_yaml))


def test_load_agent_unknown_tool_raises(tmp_path: Path) -> None:
    """Factory raises KeyError for unregistered tool name."""
    # Arrange
    bad_yaml = tmp_path / "bad_tool.yaml"
    bad_yaml.write_text(
        "name: bad\noutput_type: DerivationCode\ndeps_type: CoderDeps\nretries: 1\n"
        "tools:\n  - nonexistent_tool\nsystem_prompt: test\n"
    )
    # Act & Assert
    with pytest.raises(KeyError, match="Unknown tool"):
        load_agent(str(bad_yaml))


def test_all_five_agents_load_successfully() -> None:
    """Smoke test: all 5 production agent configs load without error."""
    # Arrange
    configs = [
        "config/agents/coder.yaml",
        "config/agents/qc_programmer.yaml",
        "config/agents/debugger.yaml",
        "config/agents/auditor.yaml",
        "config/agents/spec_interpreter.yaml",
    ]
    # Act & Assert
    for config_path in configs:
        agent = load_agent(config_path)
        assert agent.name is not None
