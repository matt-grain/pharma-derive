"""Tests for src/verification/comparator.py — double-programming verification."""

from __future__ import annotations

import pandas as pd
import pytest

from src.domain.models import QCVerdict
from src.verification.comparator import compute_ast_similarity, verify_derivation


@pytest.fixture
def two_col_df() -> pd.DataFrame:
    return pd.DataFrame({"age": [10, 25, 70, 50, 38], "score": [1.0, 2.0, 3.0, 4.0, 5.0]})


def test_verify_derivation_both_match(two_col_df: pd.DataFrame) -> None:
    # Use structurally different approaches to stay below independence_threshold
    coder_code = "df['age'] * 2"
    qc_code = "pd.Series([v * 2 for v in df['age']], index=df.index)"
    result = verify_derivation("AGE_DOUBLE", coder_code, qc_code, two_col_df, list(two_col_df.columns))

    assert result.verdict == QCVerdict.MATCH
    assert result.recommendation == "auto_approve"
    assert result.comparison is not None
    assert result.comparison.mismatch_count == 0


def test_verify_derivation_mismatch(two_col_df: pd.DataFrame) -> None:
    coder_code = "df['age'] * 2"
    qc_code = "df['age'] * 3"
    result = verify_derivation("AGE_DOUBLE", coder_code, qc_code, two_col_df, list(two_col_df.columns))

    assert result.verdict == QCVerdict.MISMATCH
    assert result.recommendation == "needs_debug"


def test_verify_derivation_identical_code_flags_independence(two_col_df: pd.DataFrame) -> None:
    # Identical code → high AST similarity → INSUFFICIENT_INDEPENDENCE
    code = "df['age'] * 2"
    result = verify_derivation("AGE_DOUBLE", code, code, two_col_df, list(two_col_df.columns))

    assert result.verdict == QCVerdict.INSUFFICIENT_INDEPENDENCE
    assert result.recommendation == "insufficient_independence"
    assert result.ast_similarity > 0.8


def test_verify_derivation_coder_fails(two_col_df: pd.DataFrame) -> None:
    result = verify_derivation("X", "df['nonexistent_col_xyz']", "df['age'] * 2", two_col_df, list(two_col_df.columns))

    assert result.verdict == QCVerdict.MISMATCH
    assert result.primary_result.success is False
    assert result.comparison is None


def test_compute_ast_similarity_identical() -> None:
    code = "df['age'] * 2"
    similarity = compute_ast_similarity(code, code)

    assert similarity == pytest.approx(1.0)  # type: ignore[misc]  # pytest stubs are incomplete


def test_compute_ast_similarity_different() -> None:
    # Simple expression vs list comprehension — structurally very different ASTs
    similarity = compute_ast_similarity("x + 1", "[v for v in range(10) if v % 2 == 0]")

    assert similarity < 0.5


def test_compute_ast_similarity_renamed_vars() -> None:
    # Same structure, different names — should be similar but not 1.0
    code_a = "df['age'] + 1"
    code_b = "df['score'] + 1"
    similarity = compute_ast_similarity(code_a, code_b)

    # AST includes variable names, so similarity is high but < 1.0
    assert 0.5 < similarity < 1.0
