"""Unit tests for DAG engine."""

from __future__ import annotations

import pytest

from src.domain.dag import DerivationDAG
from src.domain.models import DerivationRule, DerivationStatus, OutputDType


def _rule(variable: str, source_columns: list[str]) -> DerivationRule:
    return DerivationRule(
        variable=variable,
        source_columns=source_columns,
        logic=f"derive {variable}",
        output_type=OutputDType.STR,
    )


def test_build_dag_simple_linear_chain() -> None:
    # Arrange
    rules = [
        _rule("A", ["x"]),
        _rule("B", ["A"]),
        _rule("C", ["B"]),
    ]

    # Act
    dag = DerivationDAG(rules, source_columns={"x"})

    # Assert
    assert len(dag.layers) == 3
    assert dag.layers[0] == ["A"]
    assert dag.layers[1] == ["B"]
    assert dag.layers[2] == ["C"]


def test_build_dag_parallel_layer() -> None:
    # Arrange
    rules = [
        _rule("A", ["x"]),
        _rule("B", ["y"]),
        _rule("C", ["A", "B"]),
    ]

    # Act
    dag = DerivationDAG(rules, source_columns={"x", "y"})

    # Assert
    assert len(dag.layers) == 2
    assert set(dag.layers[0]) == {"A", "B"}
    assert dag.layers[1] == ["C"]


def test_build_dag_from_simple_mock_spec(
    sample_rules: list[DerivationRule],
    sample_source_columns: set[str],
) -> None:
    # Act
    dag = DerivationDAG(sample_rules, sample_source_columns)

    # Assert
    assert len(dag.layers) == 3


def test_dag_layers_correct_order(
    sample_rules: list[DerivationRule],
    sample_source_columns: set[str],
) -> None:
    # Act
    dag = DerivationDAG(sample_rules, sample_source_columns)

    # Assert
    assert set(dag.layers[0]) == {"AGE_GROUP", "TREATMENT_DURATION"}
    assert dag.layers[1] == ["IS_ELDERLY"]
    assert dag.layers[2] == ["RISK_SCORE"]


def test_dag_execution_order_respects_dependencies(
    sample_rules: list[DerivationRule],
    sample_source_columns: set[str],
) -> None:
    # Act
    dag = DerivationDAG(sample_rules, sample_source_columns)
    order = dag.execution_order

    # Assert
    assert order.index("AGE_GROUP") < order.index("IS_ELDERLY")
    assert order.index("IS_ELDERLY") < order.index("RISK_SCORE")
    assert order.index("TREATMENT_DURATION") < order.index("RISK_SCORE")


def test_dag_cycle_detection_raises() -> None:
    # Arrange
    rules = [
        _rule("A", ["B"]),
        _rule("B", ["A"]),
    ]

    # Act & Assert
    with pytest.raises(ValueError, match="Circular dependency detected"):
        DerivationDAG(rules, source_columns=set())


def test_dag_unknown_source_column_raises() -> None:
    # Arrange
    rules = [_rule("A", ["nonexistent"])]

    # Act & Assert
    with pytest.raises(ValueError, match="Unknown source column: nonexistent"):
        DerivationDAG(rules, source_columns=set())


def test_dag_node_fields_are_mutable(
    sample_rules: list[DerivationRule],
    sample_source_columns: set[str],
) -> None:
    # Arrange
    dag = DerivationDAG(sample_rules, sample_source_columns)
    node = dag.get_node("AGE_GROUP")

    # Act
    node.status = DerivationStatus.IN_PROGRESS

    # Assert
    assert dag.get_node("AGE_GROUP").status == DerivationStatus.IN_PROGRESS


def test_apply_run_result_updates_all_node_fields(
    sample_rules: list[DerivationRule],
    sample_source_columns: set[str],
) -> None:
    """apply_run_result atomically sets all fields from a DerivationRunResult."""
    # Arrange
    from src.domain.models import DerivationRunResult, QCVerdict

    dag = DerivationDAG(sample_rules, sample_source_columns)
    result = DerivationRunResult(
        variable="AGE_GROUP",
        status=DerivationStatus.APPROVED,
        coder_code="pd.cut(df['age'], bins=[0,18,65,200])",
        coder_approach="pd.cut",
        qc_code="np.select(...)",
        qc_approach="np.select",
        qc_verdict=QCVerdict.MATCH,
        approved_code="pd.cut(df['age'], bins=[0,18,65,200])",
        debug_analysis=None,
    )

    # Act
    dag.apply_run_result(result)

    # Assert
    node = dag.get_node("AGE_GROUP")
    assert node.status == DerivationStatus.APPROVED
    assert node.coder_code == "pd.cut(df['age'], bins=[0,18,65,200])"
    assert node.qc_verdict == QCVerdict.MATCH
    assert node.approved_code == "pd.cut(df['age'], bins=[0,18,65,200])"


def test_apply_run_result_partial_fields_preserves_existing(
    sample_rules: list[DerivationRule],
    sample_source_columns: set[str],
) -> None:
    """apply_run_result with None fields does not overwrite existing values."""
    # Arrange
    from src.domain.models import DerivationRunResult

    dag = DerivationDAG(sample_rules, sample_source_columns)
    dag.get_node("AGE_GROUP").coder_code = "existing_code"
    result = DerivationRunResult(
        variable="AGE_GROUP",
        status=DerivationStatus.QC_MISMATCH,
        coder_code=None,  # Should NOT overwrite "existing_code"
    )

    # Act
    dag.apply_run_result(result)

    # Assert
    node = dag.get_node("AGE_GROUP")
    assert node.status == DerivationStatus.QC_MISMATCH
    assert node.coder_code == "existing_code"  # preserved
