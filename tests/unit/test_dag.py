"""Unit tests for DAG engine."""

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
    rules = [
        _rule("A", ["x"]),
        _rule("B", ["A"]),
        _rule("C", ["B"]),
    ]
    dag = DerivationDAG(rules, source_columns={"x"})
    assert len(dag.layers) == 3
    assert dag.layers[0] == ["A"]
    assert dag.layers[1] == ["B"]
    assert dag.layers[2] == ["C"]


def test_build_dag_parallel_layer() -> None:
    rules = [
        _rule("A", ["x"]),
        _rule("B", ["y"]),
        _rule("C", ["A", "B"]),
    ]
    dag = DerivationDAG(rules, source_columns={"x", "y"})
    assert len(dag.layers) == 2
    assert set(dag.layers[0]) == {"A", "B"}
    assert dag.layers[1] == ["C"]


def test_build_dag_from_simple_mock_spec(
    sample_rules: list[DerivationRule],
    sample_source_columns: set[str],
) -> None:
    dag = DerivationDAG(sample_rules, sample_source_columns)
    assert len(dag.layers) == 3


def test_dag_layers_correct_order(
    sample_rules: list[DerivationRule],
    sample_source_columns: set[str],
) -> None:
    dag = DerivationDAG(sample_rules, sample_source_columns)
    assert set(dag.layers[0]) == {"AGE_GROUP", "TREATMENT_DURATION"}
    assert dag.layers[1] == ["IS_ELDERLY"]
    assert dag.layers[2] == ["RISK_SCORE"]


def test_dag_execution_order_respects_dependencies(
    sample_rules: list[DerivationRule],
    sample_source_columns: set[str],
) -> None:
    dag = DerivationDAG(sample_rules, sample_source_columns)
    order = dag.execution_order
    assert order.index("AGE_GROUP") < order.index("IS_ELDERLY")
    assert order.index("IS_ELDERLY") < order.index("RISK_SCORE")
    assert order.index("TREATMENT_DURATION") < order.index("RISK_SCORE")


def test_dag_cycle_detection_raises() -> None:
    rules = [
        _rule("A", ["B"]),
        _rule("B", ["A"]),
    ]
    with pytest.raises(ValueError, match="Circular dependency detected"):
        DerivationDAG(rules, source_columns=set())


def test_dag_unknown_source_column_raises() -> None:
    rules = [_rule("A", ["nonexistent"])]
    with pytest.raises(ValueError, match="Unknown source column: nonexistent"):
        DerivationDAG(rules, source_columns=set())


def test_dag_update_node_status(
    sample_rules: list[DerivationRule],
    sample_source_columns: set[str],
) -> None:
    dag = DerivationDAG(sample_rules, sample_source_columns)
    dag.update_node("AGE_GROUP", status=DerivationStatus.IN_PROGRESS)
    assert dag.get_node("AGE_GROUP").status == DerivationStatus.IN_PROGRESS

    dag.update_node("AGE_GROUP", coder_code="df['age'].map(...)")
    assert dag.get_node("AGE_GROUP").coder_code == "df['age'].map(...)"
