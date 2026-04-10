"""Safe code execution and result comparison for derivation double-programming.

Lives in domain/ — no framework dependencies beyond pandas/numpy.
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel

from src.domain.models import QCVerdict


class ExecutionResult(BaseModel, frozen=True):
    """Result of executing a single derivation expression."""

    success: bool
    series_json: str | None = None
    null_count: int = 0
    dtype: str = ""
    value_counts: dict[str, int] = {}
    error: str | None = None
    execution_time_ms: float = 0.0


class ComparisonResult(BaseModel, frozen=True):
    """Row-level comparison between primary and QC derivation outputs."""

    variable: str
    verdict: QCVerdict
    match_count: int
    mismatch_count: int
    total_rows: int
    divergent_indices: list[int]
    primary_sample: dict[str, str] = {}
    qc_sample: dict[str, str] = {}
    code_similarity: float = 0.0


def execute_derivation(
    df: pd.DataFrame,
    code: str,
    available_columns: list[str],
) -> ExecutionResult:
    """Execute a derivation expression in a restricted namespace.

    The expression is evaluated with only df, pd, and np available.
    No builtins are exposed — __import__ and similar are blocked.
    """
    start = time.perf_counter()
    try:
        # pd/np/df in globals so lambda closures can resolve them
        result = eval(code, {"__builtins__": {}, "df": df, "pd": pd, "np": np})  # noqa: S307 — sandboxed eval: restricted builtins, no __import__
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
        elapsed = (time.perf_counter() - start) * 1000
        return ExecutionResult(success=False, error=str(exc), execution_time_ms=elapsed)

    elapsed = (time.perf_counter() - start) * 1000

    if not isinstance(result, pd.Series):
        return ExecutionResult(
            success=False,
            error=f"Expected Series, got {type(result).__name__}",
            execution_time_ms=elapsed,
        )

    result_typed: pd.Series[Any] = result  # type: ignore[assignment]  # isinstance checked above; pandas stubs don't narrow
    return _build_success_result(result_typed, elapsed)


def _build_success_result(result: pd.Series[Any], elapsed: float) -> ExecutionResult:
    """Build ExecutionResult from a successful eval result."""
    vc = _build_value_counts(result)
    return ExecutionResult(
        success=True,
        series_json=result.to_json(),
        null_count=int(result.isna().sum()),
        dtype=str(result.dtype),
        value_counts=vc,
        execution_time_ms=elapsed,
    )


def _build_value_counts(series: pd.Series[Any]) -> dict[str, int]:
    """Return top-20 value counts for categorical or low-cardinality series."""
    if not pd.api.types.is_numeric_dtype(series) or series.nunique() <= 20:
        return {str(k): int(v) for k, v in series.value_counts(dropna=False).head(20).items()}
    return {}


def compare_results(
    variable: str,
    primary: pd.Series[Any],
    qc: pd.Series[Any],
    tolerance: float = 0.0,
) -> ComparisonResult:
    """Compare primary and QC Series element-wise.

    NaN == NaN is treated as equal (both_nan mask).
    Numeric columns support an absolute tolerance threshold.
    """
    both_nan = primary.isna() & qc.isna()

    if pd.api.types.is_numeric_dtype(primary) and tolerance > 0:
        within_tolerance = (primary - qc).abs() <= tolerance
        matches = both_nan | within_tolerance
    else:
        # NaN == NaN is False in pandas; both_nan handles that case
        matches = both_nan | (primary == qc)

    match_mask: pd.Series[bool] = matches.fillna(False)  # type: ignore[assignment]  # pandas fillna returns untyped
    divergent: pd.Series[bool] = ~match_mask
    divergent_idx = [int(i) for i in divergent[divergent].index]

    verdict = QCVerdict.MATCH if not divergent_idx else QCVerdict.MISMATCH

    return ComparisonResult(
        variable=variable,
        verdict=verdict,
        match_count=int(match_mask.sum()),
        mismatch_count=int(divergent.sum()),
        total_rows=len(primary),
        divergent_indices=divergent_idx,
    )
