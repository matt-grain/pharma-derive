"""inspect_data tool — returns schema, null counts, and value ranges for the agent."""

from __future__ import annotations

import pandas as pd
from pydantic_ai import RunContext  # noqa: TC002 — needed at runtime for PydanticAI get_type_hints() tool registration

from src.agents.deps import CoderDeps  # noqa: TC001 — needed at runtime for PydanticAI tool registration
from src.agents.tools.tracing import traced_tool


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


@traced_tool("inspect_data")
async def inspect_data(ctx: RunContext[CoderDeps]) -> str:
    """Return schema, null counts, and value ranges. Never exposes raw patient rows."""
    df = ctx.deps.df
    cols = ctx.deps.available_columns

    schema = _build_schema_section(df, cols)
    nulls = _build_nulls_section(df, cols)
    ranges = _build_ranges_section(df, cols)
    synthetic = f"=== SYNTHETIC SAMPLE ===\n{ctx.deps.synthetic_csv}"

    return "\n\n".join([schema, nulls, ranges, synthetic])
