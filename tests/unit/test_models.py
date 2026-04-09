"""Unit tests for domain models."""

import pytest
from pydantic import ValidationError

from src.domain.models import (
    AuditRecord,
    DAGNode,
    DerivationRule,
    DerivationStatus,
    OutputDType,
    QCVerdict,
    SourceConfig,
    SpecMetadata,
    TransformationSpec,
    WorkflowStep,
)


def test_derivation_rule_frozen_raises_on_mutation() -> None:
    rule = DerivationRule(
        variable="AGE_GROUP",
        source_columns=["age"],
        logic="categorize age",
        output_type=OutputDType.STR,
    )
    with pytest.raises(ValidationError):
        rule.variable = "OTHER"  # type: ignore[misc]


def test_transformation_spec_from_valid_data() -> None:
    spec = TransformationSpec(
        metadata=SpecMetadata(study="test", description="test spec"),
        source=SourceConfig(format="csv", path="data/", domains=["dm"]),
        derivations=[
            DerivationRule(
                variable="X",
                source_columns=["a"],
                logic="derive X from a",
                output_type=OutputDType.INT,
            ),
        ],
    )
    assert spec.metadata.study == "test"
    assert len(spec.derivations) == 1
    assert spec.derivations[0].variable == "X"


def test_dag_node_status_updates() -> None:
    rule = DerivationRule(
        variable="X",
        source_columns=["a"],
        logic="derive",
        output_type=OutputDType.STR,
    )
    node = DAGNode(rule=rule)
    assert node.status == DerivationStatus.PENDING

    node.status = DerivationStatus.IN_PROGRESS
    assert node.status == DerivationStatus.IN_PROGRESS

    node.coder_code = "df['X'] = df['a'].str.upper()"
    assert node.coder_code is not None


def test_workflow_step_enum_values() -> None:
    expected = {
        "created",
        "spec_review",
        "dag_built",
        "deriving",
        "verifying",
        "debugging",
        "review",
        "auditing",
        "completed",
        "failed",
    }
    actual = {step.value for step in WorkflowStep}
    assert actual == expected


def test_qc_verdict_enum_values() -> None:
    expected = {"match", "mismatch", "insufficient_independence"}
    actual = {v.value for v in QCVerdict}
    assert actual == expected


def test_audit_record_frozen() -> None:
    record = AuditRecord(
        timestamp="2026-04-09T10:00:00Z",
        workflow_id="wf-001",
        variable="AGE_GROUP",
        action="code_generated",
        agent="coder",
        details={"approach": "pandas cut"},
    )
    with pytest.raises(ValidationError):
        record.timestamp = "other"  # type: ignore[misc]
    assert record.details["approach"] == "pandas cut"
