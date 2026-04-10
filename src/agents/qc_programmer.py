"""QC programmer agent — independent verification using an alternative approach."""

from __future__ import annotations

from pydantic_ai import Agent

from src.agents.derivation_coder import DerivationCode
from src.agents.tools import CoderDeps, execute_code, inspect_data

qc_agent: Agent[CoderDeps, DerivationCode] = Agent(
    "test",  # overridden at call time via model= parameter
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
