"""Shared tools for Coder and QC agents.

Both tools enforce data privacy — they return only aggregates, never raw rows.
"""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, cast

import numpy as np
import pandas as pd
from pydantic_ai import RunContext  # noqa: TC002 — needed at runtime for PydanticAI get_type_hints() tool registration

if TYPE_CHECKING:
    from src.domain.models import DerivationRule

# Builtins permitted inside execute_code sandbox.
# Deliberately minimal — no I/O, no import, no introspection.
_SAFE_BUILTINS: Final[dict[str, Any]] = {
    "len": len,
    "range": range,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
    "None": None,
    "True": True,
    "False": False,
    "isinstance": isinstance,
    "type": type,
    "min": min,
    "max": max,
    "sum": sum,
    "abs": abs,
    "round": round,
    "sorted": sorted,
    "enumerate": enumerate,
    "zip": zip,
    "map": map,
    "filter": filter,
    "print": print,
}

_BLOCKED_TOKENS: Final[frozenset[str]] = frozenset(
    {"import", "open", "eval", "exec", "__import__", "compile", "globals", "locals", "getattr", "setattr", "delattr"}
)


@dataclass
class CoderDeps:
    """Dependencies injected into Coder and QC agents."""

    df: pd.DataFrame
    synthetic_csv: str
    rule: DerivationRule
    available_columns: list[str]


def _build_schema_section(df: pd.DataFrame, columns: list[str]) -> str:
    lines = ["=== SCHEMA ==="]
    for col in columns:
        if col in df.columns:
            lines.append(f"  {col}: {df[col].dtype}")
    return "\n".join(lines)


def _build_nulls_section(df: pd.DataFrame, columns: list[str]) -> str:
    lines = ["=== NULLS ==="]
    for col in columns:
        if col in df.columns:
            null_count = int(df[col].isnull().sum())
            pct = round(null_count / max(len(df), 1) * 100, 1)
            lines.append(f"  {col}: {null_count} nulls ({pct}%)")
    return "\n".join(lines)


def _build_ranges_section(df: pd.DataFrame, columns: list[str]) -> str:
    lines = ["=== RANGES ==="]
    for col in columns:
        if col not in df.columns:
            continue
        series = df[col].dropna()
        if series.empty:
            lines.append(f"  {col}: all null")
        elif pd.api.types.is_numeric_dtype(series):
            lines.append(f"  {col}: min={series.min()}, max={series.max()}, mean={round(float(series.mean()), 3)}")
        else:
            n_unique = len(series.unique())
            n_rows = len(df)
            # Omit sample values when cardinality equals row count — column is likely
            # a subject identifier. Also omit high-cardinality columns to avoid
            # leaking quasi-identifiers.
            is_id_column = n_unique == n_rows
            is_high_cardinality = n_unique > 10
            if is_id_column or is_high_cardinality:
                lines.append(f"  {col}: {n_unique} unique (sample omitted)")
            else:
                unique_vals = series.unique()[:5].tolist()
                lines.append(f"  {col}: {n_unique} unique, sample={unique_vals}")
    return "\n".join(lines)


async def inspect_data(ctx: RunContext[CoderDeps]) -> str:
    """Return schema, null counts, and value ranges. Never exposes raw patient rows."""
    df = ctx.deps.df
    cols = ctx.deps.available_columns

    schema = _build_schema_section(df, cols)
    nulls = _build_nulls_section(df, cols)
    ranges = _build_ranges_section(df, cols)
    synthetic = f"=== SYNTHETIC SAMPLE ===\n{ctx.deps.synthetic_csv}"

    return "\n\n".join([schema, nulls, ranges, synthetic])


def _check_blocked_tokens(code: str) -> str | None:
    """Return an error string if any blocked token is found in the code."""
    for token in _BLOCKED_TOKENS:
        if token in code:
            return f"BLOCKED: '{token}' is not permitted in sandboxed execution."
    return None


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


async def execute_code(ctx: RunContext[CoderDeps], code: str) -> str:
    """Execute Python code on the dataset; return aggregate summary only.

    The namespace exposes: df, pd, np.
    Dangerous builtins (import, open, eval, exec, …) are blocked.
    Returns the result summary or an error message.
    """
    block_msg = _check_blocked_tokens(code)
    if block_msg is not None:
        return block_msg

    local_ns: dict[str, Any] = {
        "df": ctx.deps.df.copy(),
        "pd": pd,
        "np": np,
    }
    globals_ns: dict[str, Any] = {"__builtins__": _SAFE_BUILTINS}

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

    if "result" not in local_ns:
        captured = stdout_buf.getvalue()
        return captured if captured else "(code ran but produced no result variable or output)"

    result = local_ns["result"]
    if not isinstance(result, pd.Series):
        return f"result type: {type(result).__name__}, value: {result!r}"

    return _summarise_result(cast("pd.Series[Any]", result))
