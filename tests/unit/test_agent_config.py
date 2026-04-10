"""Tests for agent configuration and LLM gateway.

Verifies output types, tool registration, and system prompt content.
No LLM calls are made.
"""

from __future__ import annotations

from src.agents.auditor import auditor_agent
from src.agents.debugger import debugger_agent
from src.agents.deps import AuditorDeps
from src.agents.derivation_coder import coder_agent
from src.agents.qc_programmer import qc_agent
from src.agents.spec_interpreter import spec_interpreter_agent
from src.agents.types import DebugAnalysis, DerivationCode, SpecInterpretation
from src.domain.models import AuditSummary, SpecMetadata
from tests.unit.conftest import get_system_prompts, get_tool_names

# ---------------------------------------------------------------------------
# Output type tests
# ---------------------------------------------------------------------------


def test_spec_interpreter_agent_has_correct_output_type() -> None:
    # Act & Assert
    assert spec_interpreter_agent.output_type is SpecInterpretation


def test_coder_agent_has_correct_output_type() -> None:
    # Act & Assert
    assert coder_agent.output_type is DerivationCode


def test_qc_agent_has_correct_output_type() -> None:
    # Act & Assert
    assert qc_agent.output_type is DerivationCode


def test_debugger_agent_has_correct_output_type() -> None:
    # Act & Assert
    assert debugger_agent.output_type is DebugAnalysis


def test_auditor_agent_has_correct_output_type() -> None:
    # Act & Assert
    assert auditor_agent.output_type is AuditSummary


# ---------------------------------------------------------------------------
# Tool registration tests
# ---------------------------------------------------------------------------


def test_coder_agent_has_inspect_and_execute_tools() -> None:
    # Act
    tool_names = get_tool_names(coder_agent)

    # Assert
    assert "inspect_data" in tool_names
    assert "execute_code" in tool_names


def test_qc_agent_has_inspect_and_execute_tools() -> None:
    # Act
    tool_names = get_tool_names(qc_agent)

    # Assert
    assert "inspect_data" in tool_names
    assert "execute_code" in tool_names


def test_qc_agent_system_prompt_mentions_different_approach() -> None:
    # Act
    combined = get_system_prompts(qc_agent)

    # Assert
    assert "different" in combined or "independent" in combined


def test_debugger_agent_has_no_tools() -> None:
    # Act & Assert
    assert len(get_tool_names(debugger_agent)) == 0


def test_auditor_agent_has_no_tools() -> None:
    # Act & Assert
    assert len(get_tool_names(auditor_agent)) == 0


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
    # Act & Assert
    assert auditor_agent.name == "auditor"
    assert coder_agent.name == "coder"
    assert qc_agent.name == "qc_programmer"
    assert debugger_agent.name == "debugger"
    assert spec_interpreter_agent.name == "spec_interpreter"
