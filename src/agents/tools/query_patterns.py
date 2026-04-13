"""query_patterns tool — fetches recent approved patterns for the same variable type."""

from __future__ import annotations

from pydantic_ai import RunContext  # noqa: TC002 — needed at runtime for PydanticAI get_type_hints() tool registration

from src.agents.deps import CoderDeps  # noqa: TC001 — needed at runtime for PydanticAI tool registration
from src.agents.tools.tracing import traced_tool


def _format_pattern(i: int, study: str, approach: str, approved_code: str) -> str:
    return f"=== PATTERN {i} (study={study}, approach={approach}) ===\n{approved_code}"


@traced_tool("query_patterns")
async def query_patterns(ctx: RunContext[CoderDeps]) -> str:
    """Return up to 3 approved patterns for the same variable type from long-term memory.

    Call this before writing derivation code — if a good match exists, adapt it
    rather than generating from scratch. Returns a human-readable message when no
    session or no history is available.
    """
    session = ctx.deps.session
    if session is None:
        return "No pattern history available."

    from src.persistence.pattern_repo import PatternRepository

    variable_type = ctx.deps.rule.variable
    records = await PatternRepository(session).query_by_type(variable_type=variable_type, limit=3)

    if not records:
        return "No prior patterns found for this variable."

    return "\n\n".join(_format_pattern(i + 1, r.study, r.approach, r.approved_code) for i, r in enumerate(records))
