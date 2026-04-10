"""Tests for the per-variable derivation runner."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd

from src.agents.debugger import DebugAnalysis
from src.agents.derivation_coder import DerivationCode
from src.domain.dag import DerivationDAG
from src.domain.executor import ExecutionResult
from src.domain.models import (
    ConfidenceLevel,
    CorrectImplementation,
    DerivationRule,
    DerivationStatus,
    OutputDType,
    QCVerdict,
    VerificationRecommendation,
)
from src.engine.derivation_runner import (
    _apply_approved,  # pyright: ignore[reportPrivateUsage]  # testing private helpers
    _apply_debug_fix,  # pyright: ignore[reportPrivateUsage]
    _resolve_approved_code,  # pyright: ignore[reportPrivateUsage]
)
from src.verification.comparator import VerificationResult


def _make_coder(code: str = "df['age'] + 1") -> DerivationCode:
    return DerivationCode(variable_name="X", python_code=code, approach="add", null_handling="none")


def _make_qc(code: str = "df['age'].add(1)") -> DerivationCode:
    return DerivationCode(variable_name="X", python_code=code, approach="add method", null_handling="none")


def _make_analysis(
    correct: CorrectImplementation = CorrectImplementation.CODER,
    fix: str = "",
) -> DebugAnalysis:
    return DebugAnalysis(
        variable_name="X",
        root_cause="test",
        correct_implementation=correct,
        suggested_fix=fix,
        confidence=ConfidenceLevel.HIGH,
    )


# ---------------------------------------------------------------------------
# _resolve_approved_code
# ---------------------------------------------------------------------------


def test_resolve_approved_code_suggested_fix_preferred() -> None:
    """When suggested_fix has content, return it regardless of correct_implementation."""
    # Arrange
    coder = _make_coder()
    qc = _make_qc()
    analysis = _make_analysis(correct=CorrectImplementation.QC, fix="df['age'] + 2")

    # Act
    result = _resolve_approved_code(analysis, coder, qc)

    # Assert
    assert result == "df['age'] + 2"


def test_resolve_approved_code_coder_selected() -> None:
    """correct_implementation=CODER, no suggested_fix returns coder.python_code."""
    # Arrange
    coder = _make_coder("df['age'] + 1")
    qc = _make_qc("df['age'].add(1)")
    analysis = _make_analysis(correct=CorrectImplementation.CODER, fix="")

    # Act
    result = _resolve_approved_code(analysis, coder, qc)

    # Assert
    assert result == "df['age'] + 1"


def test_resolve_approved_code_qc_selected() -> None:
    """correct_implementation=QC returns qc.python_code."""
    # Arrange
    coder = _make_coder("df['age'] + 1")
    qc = _make_qc("df['age'].add(1)")
    analysis = _make_analysis(correct=CorrectImplementation.QC, fix="")

    # Act
    result = _resolve_approved_code(analysis, coder, qc)

    # Assert
    assert result == "df['age'].add(1)"


def test_resolve_approved_code_neither_returns_none() -> None:
    """correct_implementation=NEITHER returns None."""
    # Arrange
    coder = _make_coder()
    qc = _make_qc()
    analysis = _make_analysis(correct=CorrectImplementation.NEITHER, fix="")

    # Act
    result = _resolve_approved_code(analysis, coder, qc)

    # Assert
    assert result is None


# ---------------------------------------------------------------------------
# _apply_approved
# ---------------------------------------------------------------------------


def test_apply_approved_adds_column_to_df() -> None:
    """_apply_approved adds derived column to DataFrame and sets node to APPROVED."""
    # Arrange
    rules = [
        DerivationRule(variable="TEST_VAR", source_columns=["age"], logic="test", output_type=OutputDType.INT),
    ]
    dag = DerivationDAG(rules, source_columns={"age"})
    derived_df = pd.DataFrame({"age": [10, 20, 30]})

    series = pd.Series([1, 2, 3], name="TEST_VAR")
    series_json = series.to_json()

    primary_result = ExecutionResult(success=True, series_json=series_json, dtype="int64")
    qc_result = ExecutionResult(success=True, series_json=series_json, dtype="int64")
    vr = VerificationResult(
        variable="TEST_VAR",
        verdict=QCVerdict.MATCH,
        primary_result=primary_result,
        qc_result=qc_result,
        recommendation=VerificationRecommendation.AUTO_APPROVE,
    )

    # Act
    _apply_approved("TEST_VAR", dag, derived_df, vr)

    # Assert
    assert "TEST_VAR" in derived_df.columns
    assert dag.get_node("TEST_VAR").status == DerivationStatus.APPROVED


# ---------------------------------------------------------------------------
# _apply_debug_fix
# ---------------------------------------------------------------------------


@patch("src.engine.derivation_runner.execute_derivation")
def test_apply_debug_fix_success_approves_node(mock_exec: MagicMock) -> None:
    """Successful debug fix execution marks node APPROVED and adds column."""
    # Arrange
    rules = [
        DerivationRule(variable="FIX_VAR", source_columns=["age"], logic="test", output_type=OutputDType.INT),
    ]
    dag = DerivationDAG(rules, source_columns={"age"})
    derived_df = pd.DataFrame({"age": [10, 20, 30]})

    series = pd.Series([100, 200, 300], name="FIX_VAR")
    mock_exec.return_value = ExecutionResult(success=True, series_json=series.to_json(), dtype="int64")

    # Act
    _apply_debug_fix("FIX_VAR", dag, derived_df, "df['age'] * 10")

    # Assert
    assert dag.get_node("FIX_VAR").status == DerivationStatus.APPROVED
    assert "FIX_VAR" in derived_df.columns


@patch("src.engine.derivation_runner.execute_derivation")
def test_apply_debug_fix_failure_marks_mismatch(mock_exec: MagicMock) -> None:
    """Failed debug fix execution marks node QC_MISMATCH."""
    # Arrange
    rules = [
        DerivationRule(variable="FAIL_VAR", source_columns=["age"], logic="test", output_type=OutputDType.INT),
    ]
    dag = DerivationDAG(rules, source_columns={"age"})
    derived_df = pd.DataFrame({"age": [10, 20, 30]})

    mock_exec.return_value = ExecutionResult(success=False, error="syntax error")

    # Act
    _apply_debug_fix("FAIL_VAR", dag, derived_df, "bad code")

    # Assert
    assert dag.get_node("FAIL_VAR").status == DerivationStatus.QC_MISMATCH
    assert "FAIL_VAR" not in derived_df.columns
