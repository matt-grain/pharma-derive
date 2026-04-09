"""Tests for src/domain/executor.py — safe execution and result comparison."""

from __future__ import annotations

import pandas as pd
import pytest

from src.domain.executor import compare_results, execute_derivation
from src.domain.models import QCVerdict


@pytest.fixture
def simple_df() -> pd.DataFrame:
    return pd.DataFrame({"age": [10, 25, 70, None, 50], "group": ["A", "B", "A", "B", "A"]})


def test_execute_derivation_simple_expression(simple_df: pd.DataFrame) -> None:
    result = execute_derivation(simple_df, "df['age'] * 2", list(simple_df.columns))

    assert result.success is True
    assert result.dtype == "float64"
    assert result.null_count == 1


def test_execute_derivation_with_numpy(simple_df: pd.DataFrame) -> None:
    # np.where returns ndarray — must wrap in pd.Series to pass executor check
    code = "pd.Series(np.where(df['age'] > 50, 'old', 'young'), index=df.index)"
    result = execute_derivation(simple_df, code, list(simple_df.columns))

    assert result.success is True
    assert result.series_json is not None


def test_execute_derivation_invalid_code_returns_error(simple_df: pd.DataFrame) -> None:
    result = execute_derivation(simple_df, "df[unclosed", list(simple_df.columns))

    assert result.success is False
    assert result.error is not None


def test_execute_derivation_runtime_error_returns_error(simple_df: pd.DataFrame) -> None:
    result = execute_derivation(simple_df, "df['nonexistent']", list(simple_df.columns))

    assert result.success is False
    assert result.error is not None


def test_execute_derivation_restricted_namespace(simple_df: pd.DataFrame) -> None:
    # __builtins__ is {} so __import__ is not available
    result = execute_derivation(simple_df, "__import__('os')", list(simple_df.columns))

    assert result.success is False
    assert result.error is not None


def test_compare_results_exact_match() -> None:
    s = pd.Series([1, 2, 3, 4, 5])
    result = compare_results("VAR", s, s.copy())

    assert result.verdict == QCVerdict.MATCH
    assert result.mismatch_count == 0
    assert result.match_count == 5
    assert result.divergent_indices == []


def test_compare_results_mismatch() -> None:
    primary = pd.Series([1, 2, 3])
    qc = pd.Series([1, 99, 3])
    result = compare_results("VAR", primary, qc)

    assert result.verdict == QCVerdict.MISMATCH
    assert result.mismatch_count == 1
    assert 1 in result.divergent_indices


def test_compare_results_nan_equals_nan() -> None:
    primary = pd.Series([1.0, float("nan"), 3.0])
    qc = pd.Series([1.0, float("nan"), 3.0])
    result = compare_results("VAR", primary, qc)

    assert result.verdict == QCVerdict.MATCH
    assert result.mismatch_count == 0


def test_compare_results_numeric_tolerance() -> None:
    primary = pd.Series([1.0, 2.0, 3.0])
    qc = pd.Series([1.001, 2.001, 3.001])
    result = compare_results("VAR", primary, qc, tolerance=0.01)

    assert result.verdict == QCVerdict.MATCH
    assert result.mismatch_count == 0
