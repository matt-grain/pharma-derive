"""Shared fixtures for unit tests in the agents layer."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pandas as pd
import pytest
from pydantic_ai import RunContext

from src.agents.tools import CoderDeps
from src.domain.models import DerivationRule, OutputDType


@pytest.fixture
def agent_sample_df() -> pd.DataFrame:
    """Three-row patient DataFrame for agent tool tests."""
    return pd.DataFrame(
        {
            "patient_id": ["P001", "P002", "P003"],
            "age": [72, 45, None],
            "group": ["treatment", "placebo", "treatment"],
        }
    )


@pytest.fixture
def age_rule() -> DerivationRule:
    """Age-group derivation rule fixture."""
    return DerivationRule(
        variable="AGE_GROUP",
        source_columns=["age"],
        logic="If age < 18: 'minor'. If 18 <= age < 65: 'adult'. If age >= 65: 'senior'.",
        output_type=OutputDType.STR,
        allowed_values=["minor", "adult", "senior"],
    )


@pytest.fixture
def coder_deps(agent_sample_df: pd.DataFrame, age_rule: DerivationRule) -> CoderDeps:
    """CoderDeps built from the standard sample DataFrame."""
    return CoderDeps(
        df=agent_sample_df,
        synthetic_csv=agent_sample_df.head(3).to_csv(index=False),
        rule=age_rule,
        available_columns=list(agent_sample_df.columns),
    )


@pytest.fixture
def mock_ctx(coder_deps: CoderDeps) -> RunContext[CoderDeps]:
    """Mock RunContext wired with coder_deps."""
    ctx: RunContext[CoderDeps] = MagicMock(spec=RunContext)
    ctx.deps = coder_deps
    return ctx


def get_tool_names(agent: Any) -> set[str]:
    """Return registered tool names from a PydanticAI agent via its function toolset."""
    toolset = agent._function_toolset  # private attr — Any-typed parameter bypasses pyright check
    return set(toolset.tools.keys())


def get_system_prompts(agent: Any) -> str:
    """Return combined system prompt text from an agent."""
    prompts = agent._system_prompts  # private attr — Any-typed parameter bypasses pyright check
    return " ".join(str(p) for p in prompts).lower()
