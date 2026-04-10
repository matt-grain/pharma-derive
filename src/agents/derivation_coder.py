"""Derivation coder agent — generates primary pandas implementation for each variable."""

from __future__ import annotations

from pydantic import BaseModel
from pydantic_ai import Agent

from src.agents.deps import CoderDeps
from src.agents.tools import execute_code, inspect_data


class DerivationCode(BaseModel, frozen=True):
    """Structured output of the derivation coder and QC programmer agents."""

    variable_name: str
    python_code: str
    approach: str
    null_handling: str


coder_agent: Agent[CoderDeps, DerivationCode] = Agent(
    "test",  # overridden at call time via model= parameter
    name="coder",
    output_type=DerivationCode,
    deps_type=CoderDeps,
    retries=3,
    system_prompt=(
        "You are a senior statistical programmer. Generate clean, vectorized "
        "pandas code to derive the requested variable. Your code will be "
        "executed as: `result = eval(your_code, {'df': df, 'pd': pd, 'np': np})`. "
        "The result must be a pandas Series with the same index as df. "
        "Handle null values explicitly. Use the inspect_data tool first to "
        "understand the data schema, then write the derivation."
    ),
)

coder_agent.tool(inspect_data)
coder_agent.tool(execute_code)
