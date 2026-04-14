"""query_qc_history tool — fetches recent QC verdict history for the same variable type."""

from __future__ import annotations

from typing import Final

from pydantic_ai import RunContext  # noqa: TC002 — needed at runtime for PydanticAI get_type_hints() tool registration

from src.agents.deps import CoderDeps  # noqa: TC001 — needed at runtime for PydanticAI tool registration
from src.agents.tools.tracing import traced_tool

_VERDICT_PHRASES: Final[dict[str, str]] = {
    "match": "Coder and QC agreed on this implementation — safe pattern to repeat.",
    "mismatch": (
        "Coder and QC disagreed. The debugger resolved this mismatch in a previous run. Watch for the same edge case."
    ),
}


def _format_qc_history(i: int, variable: str, study: str, verdict: str, coder_approach: str, qc_approach: str) -> str:
    verdict_phrase = _VERDICT_PHRASES.get(verdict, f"Verdict: {verdict}.")
    return (
        f"=== QC HISTORY {i} (variable={variable}, study={study}, verdict={verdict}) ===\n"
        f"Coder approach: {coder_approach}\n"
        f"QC approach: {qc_approach}\n"
        f"{verdict_phrase}"
    )


@traced_tool("query_qc_history")
async def query_qc_history(ctx: RunContext[CoderDeps]) -> str:
    """Return up to 3 recent QC verdict records for the same variable type.

    Call this before writing derivation code — prior coder/QC disagreements reveal
    edge cases to avoid. Returns a human-readable message when no repo is wired or
    no history exists.
    """
    repo = ctx.deps.qc_history_repo
    if repo is None:
        return "No QC history available."

    variable = ctx.deps.rule.variable
    records = await repo.query_by_variable(variable=variable, limit=3)

    if not records:
        return "No prior QC history for this variable."

    return "\n\n".join(
        _format_qc_history(i + 1, r.variable, r.study, r.verdict, r.coder_approach, r.qc_approach)
        for i, r in enumerate(records)
    )
