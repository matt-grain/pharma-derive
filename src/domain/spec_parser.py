"""Spec parser — parse YAML spec files, load source data, generate synthetic datasets."""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd
import yaml

from src.domain.models import (
    DerivationRule,
    GroundTruthConfig,
    SourceConfig,
    SpecMetadata,
    SyntheticConfig,
    ToleranceConfig,
    TransformationSpec,
    ValidationConfig,
)

_DATE_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_spec(spec_path: str | Path) -> TransformationSpec:
    """Parse a YAML spec file into a TransformationSpec model."""
    path = Path(spec_path)
    if not path.exists():
        msg = f"Spec file not found: {path}"
        raise FileNotFoundError(msg)

    with path.open() as f:
        loaded: object = yaml.safe_load(f)

    if not isinstance(loaded, dict):
        msg = f"Invalid spec format: expected a YAML mapping, got {type(loaded).__name__}"
        raise ValueError(msg)

    raw: dict[str, Any] = dict(loaded)  # type: ignore[arg-type]  # YAML safe_load returns untyped dict

    metadata = SpecMetadata(
        study=raw["study"],
        description=raw["description"],
        version=raw.get("version", "0.1.0"),
        author=raw.get("author", ""),
    )
    source = SourceConfig(**raw["source"])

    synthetic = SyntheticConfig(**raw["synthetic"]) if "synthetic" in raw else SyntheticConfig()

    validation = ValidationConfig()
    if "validation" in raw:
        val_raw: dict[str, Any] = raw["validation"]
        gt = GroundTruthConfig(**val_raw["ground_truth"]) if "ground_truth" in val_raw else None
        tol = ToleranceConfig(**val_raw["tolerance"]) if "tolerance" in val_raw else ToleranceConfig()
        validation = ValidationConfig(ground_truth=gt, tolerance=tol)

    derivations = [DerivationRule(**d) for d in raw["derivations"]]

    return TransformationSpec(
        metadata=metadata,
        source=source,
        synthetic=synthetic,
        validation=validation,
        derivations=derivations,
    )


def load_source_data(spec: TransformationSpec) -> pd.DataFrame:
    """Load source data based on spec.source config. Supports CSV."""
    fmt = spec.source.format.lower()
    if fmt != "csv":
        msg = f"Unsupported source format: {fmt}"
        raise ValueError(msg)

    base_path = Path(spec.source.path)
    if not base_path.exists():
        msg = f"Source data path not found: {base_path}"
        raise FileNotFoundError(msg)

    frames: list[pd.DataFrame] = []
    for domain in spec.source.domains:
        file_path = base_path / f"{domain}.csv"
        if not file_path.exists():
            msg = f"Domain file not found: {file_path}"
            raise FileNotFoundError(msg)
        frames.append(pd.read_csv(file_path))

    if len(frames) == 1:
        return frames[0]

    result = frames[0]
    for frame in frames[1:]:
        result = result.merge(frame, on=spec.source.primary_key)
    return result


def get_source_columns(df: pd.DataFrame) -> set[str]:
    """Extract column names from a DataFrame as a set."""
    return set(df.columns.tolist())


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
            non_null_str: list[str] = series.dropna().astype(str).tolist()
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
