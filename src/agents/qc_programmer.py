"""QC programmer agent — independent verification using an alternative approach."""

from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from src.agents.derivation_coder import DerivationCode
from src.agents.tools import CoderDeps, execute_code, inspect_data

_model = OpenAIChatModel(
    "cdde-agent",
    provider=OpenAIProvider(base_url="http://localhost:8650/v1", api_key="not-needed-for-mailbox"),
)

qc_agent: Agent[CoderDeps, DerivationCode] = Agent(
    _model,
    output_type=DerivationCode,
    deps_type=CoderDeps,
    retries=3,
    system_prompt=(
        "You are a QC (quality control) programmer performing INDEPENDENT "
        "verification. Generate pandas code to derive the requested variable "
        "using a DIFFERENT approach than the obvious one. "
        "If the obvious approach uses pd.cut, use np.select or np.where. "
        "If the obvious approach uses conditionals, use a mapping. "
        "Your code must produce the same result but via a different path. "
        "Use the inspect_data tool first."
    ),
)

qc_agent.tool(inspect_data)
qc_agent.tool(execute_code)
