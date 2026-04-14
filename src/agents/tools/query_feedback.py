"""query_feedback tool — fetches recent human feedback for the same variable type."""

from __future__ import annotations

from typing import Final

from pydantic_ai import RunContext  # noqa: TC002 — needed at runtime for PydanticAI get_type_hints() tool registration

from src.agents.deps import CoderDeps  # noqa: TC001 — needed at runtime for PydanticAI tool registration
from src.agents.tools.tracing import traced_tool

_ACTION_PHRASES: Final[dict[str, str]] = {
    "approved": "The human reviewer approved this approach. Repeating it is safe.",
    "rejected": "The human reviewer rejected the previous coder's approach. Avoid generating similar code.",
    "overridden": (
        "The human reviewer replaced the coder's code with a different implementation. "
        "Consider this preference when generating new code."
    ),
}


def _format_feedback(i: int, variable: str, action_taken: str, study: str, feedback: str) -> str:
    action_phrase = _ACTION_PHRASES.get(action_taken, f"Action taken: {action_taken}.")
    return (
        f"=== FEEDBACK {i} (variable={variable}, action={action_taken}, study={study}) ===\n"
        f"Reason: {feedback}\n"
        f"{action_phrase}"
    )


@traced_tool("query_feedback")
async def query_feedback(ctx: RunContext[CoderDeps]) -> str:
    """Return up to 3 recent human feedback records for the same variable type.

    Call this before writing derivation code — human feedback is the STRONGEST signal.
    A rejection means do not repeat that approach. An override means adopt the reviewer's
    strategy. Returns a human-readable message when no repo is wired or no history exists.
    """
    repo = ctx.deps.feedback_repo
    if repo is None:
        return "No feedback history available."

    variable = ctx.deps.rule.variable
    records = await repo.query_by_variable(variable=variable, limit=3)

    if not records:
        return "No prior feedback found for this variable."

    return "\n\n".join(
        _format_feedback(i + 1, r.variable, r.action_taken, r.study, r.feedback) for i, r in enumerate(records)
    )
