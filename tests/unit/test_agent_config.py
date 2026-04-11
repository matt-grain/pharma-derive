"""Tests for agent configuration and LLM gateway.

Verifies output types, tool registration, and system prompt content.
Agents are loaded from YAML via load_agent() — no module-level singletons.
No LLM calls are made.
"""

from __future__ import annotations

from src.agents.deps import AuditorDeps
from src.agents.factory import load_agent
from src.agents.types import DebugAnalysis, DerivationCode, SpecInterpretation
from src.domain.models import AuditSummary, SpecMetadata
from tests.unit.conftest import get_system_prompts, get_tool_names

# ---------------------------------------------------------------------------
# Output type tests
# ---------------------------------------------------------------------------


def test_spec_interpreter_agent_has_correct_output_type() -> None:
    # Act & Assert
    agent = load_agent("config/agents/spec_interpreter.yaml")
    assert agent.output_type is SpecInterpretation


def test_coder_agent_has_correct_output_type() -> None:
    # Act & Assert
    agent = load_agent("config/agents/coder.yaml")
    assert agent.output_type is DerivationCode


def test_qc_agent_has_correct_output_type() -> None:
    # Act & Assert
    agent = load_agent("config/agents/qc_programmer.yaml")
    assert agent.output_type is DerivationCode


def test_debugger_agent_has_correct_output_type() -> None:
    # Act & Assert
    agent = load_agent("config/agents/debugger.yaml")
    assert agent.output_type is DebugAnalysis


def test_auditor_agent_has_correct_output_type() -> None:
    # Act & Assert
    agent = load_agent("config/agents/auditor.yaml")
    assert agent.output_type is AuditSummary


# ---------------------------------------------------------------------------
# Tool registration tests
# ---------------------------------------------------------------------------


def test_coder_agent_has_inspect_and_execute_tools() -> None:
    # Act
    agent = load_agent("config/agents/coder.yaml")
    tool_names = get_tool_names(agent)

    # Assert
    assert "inspect_data" in tool_names
    assert "execute_code" in tool_names


def test_qc_agent_has_inspect_and_execute_tools() -> None:
    # Act
    agent = load_agent("config/agents/qc_programmer.yaml")
    tool_names = get_tool_names(agent)

    # Assert
    assert "inspect_data" in tool_names
    assert "execute_code" in tool_names


def test_qc_agent_system_prompt_mentions_different_approach() -> None:
    # Act
    agent = load_agent("config/agents/qc_programmer.yaml")
    combined = get_system_prompts(agent)

    # Assert
    assert "different" in combined or "independent" in combined


def test_debugger_agent_has_no_tools() -> None:
    # Act & Assert
    agent = load_agent("config/agents/debugger.yaml")
    assert len(get_tool_names(agent)) == 0


def test_auditor_agent_has_no_tools() -> None:
    # Act & Assert
    agent = load_agent("config/agents/auditor.yaml")
    assert len(get_tool_names(agent)) == 0


# ---------------------------------------------------------------------------
# LLM gateway tests
# ---------------------------------------------------------------------------


def _reset_caches() -> None:
    """Clear both the LLM model cache and the settings lru_cache."""
    from src.config.llm_gateway import reset_llm_cache
    from src.config.settings import get_settings

    reset_llm_cache()
    get_settings.cache_clear()


def test_llm_gateway_creates_correct_model() -> None:
    # Arrange
    from pydantic_ai.models.openai import OpenAIChatModel

    from src.config.llm_gateway import create_llm

    _reset_caches()

    # Act
    model = create_llm()

    # Assert
    assert isinstance(model, OpenAIChatModel)


def test_llm_gateway_respects_explicit_params() -> None:
    # Arrange
    from src.config.llm_gateway import create_llm

    _reset_caches()

    # Act
    model = create_llm(model_name="my-custom-model", base_url="http://custom:9999/v1", api_key="key")

    # Assert
    assert model.model_name == "my-custom-model"


def test_llm_gateway_default_model_name() -> None:
    # Arrange
    from src.config.llm_gateway import create_llm

    _reset_caches()

    # Act
    model = create_llm()

    # Assert — default from Settings
    assert model.model_name == "cdde-agent"


# ---------------------------------------------------------------------------
# Smoke tests — dependencies and schema construction
# ---------------------------------------------------------------------------


def test_spec_metadata_is_accessible_in_auditor_deps() -> None:
    """AuditorDeps accepts a SpecMetadata without raising."""
    # Arrange
    meta = SpecMetadata(study="TEST_STUDY", description="Test", version="0.1.0", author="tester")

    # Act
    deps = AuditorDeps(dag_summary="2 derivations, 0 mismatches", workflow_id="wf-001", spec_metadata=meta)

    # Assert
    assert deps.spec_metadata.study == "TEST_STUDY"


# ---------------------------------------------------------------------------
# Agent name tests
# ---------------------------------------------------------------------------


def test_all_agents_have_name_set() -> None:
    """Every agent must have a name for audit trail metadata."""
    # Arrange
    agents = {
        "auditor": load_agent("config/agents/auditor.yaml"),
        "coder": load_agent("config/agents/coder.yaml"),
        "qc_programmer": load_agent("config/agents/qc_programmer.yaml"),
        "debugger": load_agent("config/agents/debugger.yaml"),
        "spec_interpreter": load_agent("config/agents/spec_interpreter.yaml"),
    }

    # Act & Assert
    for expected_name, agent in agents.items():
        assert agent.name == expected_name, f"Agent '{expected_name}' has name '{agent.name}'"
