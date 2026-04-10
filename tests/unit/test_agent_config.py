"""Tests for agent configuration and LLM gateway.

Verifies output types, tool registration, and system prompt content.
No LLM calls are made.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

from src.agents.auditor import AuditorDeps, auditor_agent
from src.agents.debugger import DebugAnalysis, debugger_agent
from src.agents.derivation_coder import DerivationCode, coder_agent
from src.agents.qc_programmer import qc_agent
from src.agents.spec_interpreter import SpecInterpretation, spec_interpreter_agent
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


def test_llm_gateway_creates_correct_model() -> None:
    # Arrange
    from pydantic_ai.models.openai import OpenAIChatModel

    from src.engine.llm_gateway import create_llm

    # Act
    model = create_llm()

    # Assert
    assert isinstance(model, OpenAIChatModel)


def test_llm_gateway_reads_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    monkeypatch.setenv("LLM_BASE_URL", "http://custom-host:9999/v1")
    monkeypatch.setenv("LLM_MODEL", "my-custom-model")
    monkeypatch.setenv("LLM_API_KEY", "secret-key")

    from src.engine.llm_gateway import create_llm

    # Act
    model = create_llm()

    # Assert
    assert model.model_name == "my-custom-model"


def test_llm_gateway_default_model_name() -> None:
    # Arrange
    from src.engine.llm_gateway import create_llm

    env_backup = os.environ.pop("LLM_MODEL", None)
    try:
        # Act
        model = create_llm()

        # Assert
        assert model.model_name == "cdde-agent"
    finally:
        if env_backup is not None:
            os.environ["LLM_MODEL"] = env_backup


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
