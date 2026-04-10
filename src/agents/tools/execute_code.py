"""execute_code tool — sandboxed Python execution on the agent's dataset."""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from typing import Any, cast

import pandas as pd
from pydantic_ai import RunContext  # noqa: TC002 — needed at runtime for PydanticAI get_type_hints() tool registration

from src.agents.deps import CoderDeps  # noqa: TC001 — needed at runtime for PydanticAI tool registration
from src.agents.tools.sandbox import build_sandbox, check_blocked_tokens
from src.agents.tools.tracing import traced_tool


def _summarise_result(result: pd.Series[Any]) -> str:
    """Produce an aggregate summary of the result Series — no raw row data."""
    dtype = str(result.dtype)
    null_count = int(result.isnull().sum())
    total = len(result)
    unique_count = int(result.nunique(dropna=True))

    lines = [
        f"dtype: {dtype}",
        f"length: {total}",
        f"null_count: {null_count}",
        f"unique_values: {unique_count}",
    ]

    non_null = result.dropna()
    if not non_null.empty:
        if pd.api.types.is_numeric_dtype(non_null):
            lines.append(f"min: {non_null.min()}, max: {non_null.max()}")
        else:
            sample = non_null.unique()[:5].tolist()
            lines.append(f"sample_unique: {sample}")

    return "\n".join(lines)


def _format_exec_output(local_ns: dict[str, Any], stdout_buf: io.StringIO) -> str:
    """Format execution output from the sandbox namespace."""
    if "result" not in local_ns:
        captured = stdout_buf.getvalue()
        return captured if captured else "(code ran but produced no result variable or output)"
    result = local_ns["result"]
    if not isinstance(result, pd.Series):
        return f"result type: {type(result).__name__}, value: {result!r}"
    return _summarise_result(cast("pd.Series[Any]", result))


@traced_tool("execute_code")
async def execute_code(ctx: RunContext[CoderDeps], code: str) -> str:
    """Execute Python code on the dataset; return aggregate summary only.

    The namespace exposes: df, pd, np.
    Dangerous builtins (import, open, eval, exec, …) are blocked.
    Returns the result summary or an error message.
    """
    block_msg = check_blocked_tokens(code)
    if block_msg is not None:
        return block_msg

    globals_ns, local_ns = build_sandbox(ctx.deps.df)

    stdout_buf = io.StringIO()
    try:
        with redirect_stdout(stdout_buf):
            exec(code, globals_ns, local_ns)  # noqa: S102 — sandboxed exec: restricted builtins via _SAFE_BUILTINS, blocked tokens checked
    except (
        SyntaxError,
        NameError,
        TypeError,
        ValueError,
        ArithmeticError,
        AttributeError,
        KeyError,
        IndexError,
    ) as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"

    return _format_exec_output(local_ns, stdout_buf)
