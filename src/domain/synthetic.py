"""Synthetic data generation — creates privacy-safe reference datasets from real data."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Final

import numpy as np
import pandas as pd

_DATE_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _is_date_column(series: pd.Series[Any]) -> bool:
    """Check if >80% of non-null values match YYYY-MM-DD pattern."""
    non_null = series.dropna()
    if len(non_null) == 0:
        return False
    match_count = sum(1 for v in non_null if _DATE_PATTERN.match(str(v)))
    return match_count / len(non_null) > 0.8


def _random_date_between(start: date, end: date, rng: np.random.Generator) -> str:
    """Generate a random date string between start and end (inclusive)."""
    delta_days = (end - start).days
    random_days = int(rng.integers(0, max(delta_days, 1) + 1))
    return (start + timedelta(days=random_days)).isoformat()


def generate_synthetic(df: pd.DataFrame, rows: int = 15) -> pd.DataFrame:
    """Generate a synthetic reference dataset from a real DataFrame.

    For each column:
    - Numeric: random values in [min, max] range, with ~10% nulls
    - String/object date columns: random dates between min and max
    - String/object non-date: sample from unique values with replacement
    """
    rng = np.random.default_rng(42)
    result: dict[str, list[object]] = {}

    for col in df.columns:
        series: pd.Series[Any] = df[col]
        values: list[object]

        if pd.api.types.is_numeric_dtype(series):
            col_min = float(series.min())
            col_max = float(series.max())
            if pd.api.types.is_integer_dtype(series):
                values = [int(x) for x in rng.integers(int(col_min), int(col_max) + 1, size=rows)]
            else:
                values = [float(x) for x in rng.uniform(col_min, col_max, size=rows)]
            null_mask = rng.random(rows) < 0.1
            values = [None if null_mask[i] else values[i] for i in range(rows)]

        elif _is_date_column(series):
            non_null_str: list[str] = [s for s in series.dropna().astype(str).tolist() if _DATE_PATTERN.match(s)]
            dates = [date.fromisoformat(d) for d in non_null_str]
            min_date, max_date = min(dates), max(dates)
            values = [_random_date_between(min_date, max_date, rng) for _ in range(rows)]

        else:
            uniques: list[Any] = series.dropna().unique().tolist()
            if uniques:
                indices = rng.integers(0, len(uniques), size=rows)
                values = [uniques[int(i)] for i in indices]
            else:
                values = [None] * rows

        result[col] = values

    return pd.DataFrame(result)
