"""Tests for the per-variable derivation runner."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.agents.types import DebugAnalysis, DerivationCode
from src.domain.dag import DerivationDAG
from src.domain.exceptions import DerivationError
from src.domain.executor import ExecutionResult
from src.domain.models import (
    ConfidenceLevel,
    CorrectImplementation,
    DerivationRule,
    DerivationRunResult,
    DerivationStatus,
    OutputDType,
    QCVerdict,
)
from src.engine.debug_runner import (
    _resolve_approved_code,  # pyright: ignore[reportPrivateUsage]
    apply_series_to_df,
)


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
# apply_series_to_df
# ---------------------------------------------------------------------------


def testapply_series_to_df_adds_column_to_dataframe() -> None:
    """apply_series_to_df deserializes series_json and adds column to DataFrame."""
    # Arrange
    derived_df = pd.DataFrame({"age": [10, 20, 30]})
    series = pd.Series([1, 2, 3], name="TEST_VAR")
    exec_result = ExecutionResult(success=True, series_json=series.to_json(), dtype="int64")

    # Act
    apply_series_to_df("TEST_VAR", exec_result, derived_df)

    # Assert
    assert "TEST_VAR" in derived_df.columns
    assert list(derived_df["TEST_VAR"]) == [1, 2, 3]


def testapply_series_to_df_raises_derivation_error_on_missing_json() -> None:
    """apply_series_to_df raises DerivationError when series_json is None."""
    # Arrange
    derived_df = pd.DataFrame({"age": [10, 20, 30]})
    exec_result = ExecutionResult(success=False, series_json=None, error="failed")

    # Act & Assert
    with pytest.raises(DerivationError, match="TEST_VAR"):
        apply_series_to_df("TEST_VAR", exec_result, derived_df)


# ---------------------------------------------------------------------------
# dag.apply_run_result — integration with runner output model
# ---------------------------------------------------------------------------


def test_apply_run_result_approved_sets_node_state() -> None:
    """DerivationRunResult with APPROVED status correctly updates the DAG node."""
    # Arrange
    rules = [
        DerivationRule(variable="TEST_VAR", source_columns=["age"], logic="test", output_type=OutputDType.INT),
    ]
    dag = DerivationDAG(rules, source_columns={"age"})
    result = DerivationRunResult(
        variable="TEST_VAR",
        status=DerivationStatus.APPROVED,
        coder_code="df['age'] + 1",
        coder_approach="add",
        qc_code="df['age'].add(1)",
        qc_approach="add method",
        qc_verdict=QCVerdict.MATCH,
        approved_code="df['age'] + 1",
    )

    # Act
    dag.apply_run_result(result)

    # Assert
    node = dag.get_node("TEST_VAR")
    assert node.status == DerivationStatus.APPROVED
    assert node.approved_code == "df['age'] + 1"
    assert node.qc_verdict == QCVerdict.MATCH


@patch("src.engine.derivation_runner.execute_derivation")
def test_apply_run_result_mismatch_after_failed_fix(mock_exec: MagicMock) -> None:
    """QC_MISMATCH result is applied when debug fix execution fails."""
    # Arrange
    rules = [
        DerivationRule(variable="FAIL_VAR", source_columns=["age"], logic="test", output_type=OutputDType.INT),
    ]
    dag = DerivationDAG(rules, source_columns={"age"})
    mock_exec.return_value = ExecutionResult(success=False, error="syntax error")

    result = DerivationRunResult(
        variable="FAIL_VAR",
        status=DerivationStatus.QC_MISMATCH,
        coder_code="bad code",
        qc_code="other bad code",
        qc_verdict=QCVerdict.MISMATCH,
    )

    # Act
    dag.apply_run_result(result)

    # Assert
    assert dag.get_node("FAIL_VAR").status == DerivationStatus.QC_MISMATCH
