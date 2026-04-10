"""Source data loading — reads CSV and XPT domain files into a merged DataFrame."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

import pandas as pd
import pyreadstat  # type: ignore[import-untyped]

if TYPE_CHECKING:
    from src.domain.models import TransformationSpec


def load_source_data(spec: TransformationSpec) -> pd.DataFrame:
    """Load source data based on spec.source config. Supports CSV and XPT."""
    fmt = spec.source.format.lower()
    base_path = Path(spec.source.path)
    if not base_path.exists():
        msg = f"Source data path not found: {base_path}"
        raise FileNotFoundError(msg)

    if fmt == "csv":
        frames: list[pd.DataFrame] = []
        for domain in spec.source.domains:
            file_path = base_path / f"{domain}.csv"
            if not file_path.exists():
                msg = f"Domain file not found: {file_path}"
                raise FileNotFoundError(msg)
            frames.append(pd.read_csv(file_path))
    elif fmt == "xpt":
        frames = []
        for domain in spec.source.domains:
            file_path = base_path / f"{domain}.xpt"
            if not file_path.exists():
                msg = f"Domain file not found: {file_path}"
                raise FileNotFoundError(msg)
            df_domain = cast("pd.DataFrame", pyreadstat.read_xport(str(file_path))[0])  # type: ignore[no-untyped-call]
            frames.append(df_domain)
    else:
        msg = f"Unsupported source format: {fmt}"
        raise ValueError(msg)

    if len(frames) == 1:
        return frames[0]

    result = frames[0]
    for frame in frames[1:]:
        result = result.merge(frame, on=spec.source.primary_key, how="left", suffixes=("", "_dup"))
        dup_cols = [c for c in result.columns if c.endswith("_dup")]
        result = result.drop(columns=dup_cols)
    return result


def get_source_columns(df: pd.DataFrame) -> set[str]:
    """Extract column names from a DataFrame as a set."""
    return set(df.columns.tolist())
