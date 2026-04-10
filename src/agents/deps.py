"""Shared dependency container for Coder and QC agents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pandas as pd  # noqa: TC002 — used at runtime in dataclass field

if TYPE_CHECKING:
    from src.domain.models import DerivationRule


@dataclass
class CoderDeps:
    """Dependencies injected into Coder and QC agents."""

    df: pd.DataFrame
    synthetic_csv: str
    rule: DerivationRule
    available_columns: list[str]
