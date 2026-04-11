"""Shared test fixtures for all tests."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pandas as pd
import pytest

from src.config.settings import get_settings
from src.domain.models import (
    DerivationRule,
    OutputDType,
    TransformationSpec,
)

if TYPE_CHECKING:
    from pathlib import Path

    from src.domain.dag import DerivationDAG


@pytest.fixture(autouse=True, scope="session")
def _use_test_database() -> None:  # pyright: ignore[reportUnusedFunction]
    """Force all tests to use an in-memory SQLite database instead of the real cdde.db."""
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    get_settings.cache_clear()


_PATIENTS_CSV = """\
patient_id,age,treatment_start,treatment_end,group
P001,72,2024-01-15,2024-06-20,treatment
P002,45,2024-02-01,2024-07-15,treatment
P003,38,2024-01-20,2024-05-10,placebo
P004,65,2024-03-01,,placebo
P005,55,2024-02-15,2024-08-01,treatment
P006,,2024-01-10,2024-04-30,placebo
P007,15,2024-04-01,2024-09-15,treatment
P008,81,2024-01-25,2024-06-01,placebo
"""

_SPEC_YAML = """\
study: simple_mock
description: "Minimal spec for engine development and testing"
version: "0.1.0"
author: "dev"

source:
  format: csv
  path: "{fixtures_path}"
  domains: [patients]
  primary_key: patient_id

derivations:
  - variable: AGE_GROUP
    source_columns: [age]
    logic: "If age < 18: 'minor'. If 18 <= age < 65: 'adult'. If age >= 65: 'senior'. Null if age missing."
    output_type: str
    allowed_values: ["minor", "adult", "senior"]

  - variable: TREATMENT_DURATION
    source_columns: [treatment_start, treatment_end]
    logic: >-
      Number of days between treatment_end and treatment_start
      plus 1 (inclusive). Null if either date is missing.
    output_type: float
    nullable: true

  - variable: IS_ELDERLY
    source_columns: [AGE_GROUP]
    logic: "True if AGE_GROUP is 'senior', False otherwise. Null if AGE_GROUP is null."
    output_type: bool

  - variable: RISK_SCORE
    source_columns: [IS_ELDERLY, TREATMENT_DURATION]
    logic: >-
      If IS_ELDERLY is True and TREATMENT_DURATION > 120 result is 'high'.
      Otherwise 'low'. Null if any source is null.
    output_type: str
    allowed_values: ["high", "medium", "low"]
"""


def _build_rules() -> list[DerivationRule]:
    return [
        DerivationRule(
            variable="AGE_GROUP",
            source_columns=["age"],
            logic="If age < 18: 'minor'. If 18 <= age < 65: 'adult'. If age >= 65: 'senior'. Null if age missing.",
            output_type=OutputDType.STR,
            allowed_values=["minor", "adult", "senior"],
        ),
        DerivationRule(
            variable="TREATMENT_DURATION",
            source_columns=["treatment_start", "treatment_end"],
            logic=(
                "Number of days between treatment_end and treatment_start"
                " plus 1 (inclusive). Null if either date is missing."
            ),
            output_type=OutputDType.FLOAT,
            nullable=True,
        ),
        DerivationRule(
            variable="IS_ELDERLY",
            source_columns=["AGE_GROUP"],
            logic="True if AGE_GROUP is 'senior', False otherwise. Null if AGE_GROUP is null.",
            output_type=OutputDType.BOOL,
        ),
        DerivationRule(
            variable="RISK_SCORE",
            source_columns=["IS_ELDERLY", "TREATMENT_DURATION"],
            logic=(
                "If IS_ELDERLY is True and TREATMENT_DURATION > 120, result is 'high'."
                " Otherwise 'low'. Null if any source is null."
            ),
            output_type=OutputDType.STR,
            allowed_values=["high", "medium", "low"],
        ),
    ]


@pytest.fixture
def sample_spec_path(tmp_path: Path) -> Path:
    """Write simple_mock.yaml to tmp_path and return the path."""
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    (fixtures_dir / "patients.csv").write_text(_PATIENTS_CSV)

    spec_content = _SPEC_YAML.format(fixtures_path=fixtures_dir.as_posix())
    spec_file = tmp_path / "simple_mock.yaml"
    spec_file.write_text(spec_content)
    return spec_file


@pytest.fixture
def sample_spec(sample_spec_path: Path) -> TransformationSpec:
    """Return a parsed TransformationSpec for the simple mock scenario."""
    from src.domain.spec_parser import parse_spec

    return parse_spec(sample_spec_path)


@pytest.fixture
def sample_df() -> pd.DataFrame:
    """Return a mock patients DataFrame matching simple_mock.yaml."""
    from io import StringIO

    return pd.read_csv(StringIO(_PATIENTS_CSV))


@pytest.fixture
def sample_rules() -> list[DerivationRule]:
    """Return the derivation rules from the simple mock spec."""
    return _build_rules()


@pytest.fixture
def sample_source_columns() -> set[str]:
    """Return the set of source column names from the mock DataFrame."""
    return {"patient_id", "age", "treatment_start", "treatment_end", "group"}


@pytest.fixture
def sample_dag(
    sample_rules: list[DerivationRule],
    sample_source_columns: set[str],
) -> DerivationDAG:
    """Return a built DerivationDAG from the simple mock spec rules."""
    from src.domain.dag import DerivationDAG

    return DerivationDAG(sample_rules, sample_source_columns)
