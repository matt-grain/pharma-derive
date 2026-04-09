"""Unit tests for the audit trail module."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 — used at runtime in pytest fixture parameter types
from typing import cast

import pytest

from src.audit.trail import AuditTrail


def test_audit_trail_append_only() -> None:
    # Arrange
    trail = AuditTrail("wf_test01")

    # Act
    trail.record(variable="AGE_GROUP", action="derivation_started", agent="coder")
    trail.record(variable="AGE_GROUP", action="qc_passed", agent="qc_programmer")
    trail.record(variable="IS_ELDERLY", action="derivation_started", agent="coder")

    # Assert
    assert len(trail.records) == 3


def test_audit_trail_record_generates_timestamp() -> None:
    # Arrange
    trail = AuditTrail("wf_test02")

    # Act
    rec = trail.record(variable="AGE_GROUP", action="derivation_started", agent="coder")

    # Assert — ISO 8601 with timezone offset or 'Z'
    ts = rec.timestamp
    assert "T" in ts
    assert len(ts) > 19  # must include more than just "YYYY-MM-DDTHH:MM:SS"
    assert "+" in ts or ts.endswith("+00:00") or "Z" in ts or ts.endswith("+00:00")


def test_audit_trail_get_variable_history() -> None:
    # Arrange
    trail = AuditTrail("wf_test03")
    trail.record(variable="AGE_GROUP", action="derivation_started", agent="coder")
    trail.record(variable="IS_ELDERLY", action="derivation_started", agent="coder")
    trail.record(variable="AGE_GROUP", action="qc_passed", agent="qc_programmer")

    # Act
    history = trail.get_variable_history("AGE_GROUP")

    # Assert
    assert len(history) == 2
    assert all(r.variable == "AGE_GROUP" for r in history)


def test_audit_trail_to_json_creates_file(tmp_path: Path) -> None:
    # Arrange
    trail = AuditTrail("wf_test04")
    trail.record(variable="AGE_GROUP", action="derivation_started", agent="coder")
    trail.record(variable="AGE_GROUP", action="approved", agent="orchestrator", details={"reason": "qc_match"})
    output_file = tmp_path / "audit" / "wf_test04_audit.json"

    # Act
    trail.to_json(output_file)

    # Assert
    assert output_file.exists()
    data = cast("list[dict[str, object]]", json.loads(output_file.read_text()))
    assert len(data) == 2
    assert data[0]["variable"] == "AGE_GROUP"
    first_details = data[1]["details"]
    assert isinstance(first_details, dict)
    assert first_details["reason"] == "qc_match"


def test_audit_trail_summary_counts() -> None:
    # Arrange
    trail = AuditTrail("wf_test05")
    trail.record(variable="AGE_GROUP", action="derivation_started", agent="coder")
    trail.record(variable="IS_ELDERLY", action="derivation_started", agent="coder")
    trail.record(variable="AGE_GROUP", action="qc_passed", agent="qc_programmer")
    trail.record(variable="", action="audit_complete", agent="auditor")

    # Act
    summary = trail.summary()

    # Assert
    assert summary["coder:derivation_started"] == 2
    assert summary["qc_programmer:qc_passed"] == 1
    assert summary["auditor:audit_complete"] == 1


def test_audit_trail_records_are_immutable() -> None:
    """Records property returns a copy — mutating it does not affect the trail."""
    # Arrange
    trail = AuditTrail("wf_test06")
    trail.record(variable="AGE_GROUP", action="derivation_started", agent="coder")

    # Act
    snapshot = trail.records
    snapshot.clear()

    # Assert — internal list is unaffected
    assert len(trail.records) == 1


def test_audit_trail_details_stored_correctly() -> None:
    # Arrange
    trail = AuditTrail("wf_test07")

    # Act
    rec = trail.record(
        variable="RISK_SCORE",
        action="qc_mismatch",
        agent="orchestrator",
        details={"mismatch_count": 3, "tolerance": 0.0, "retried": True},
    )

    # Assert
    assert rec.details["mismatch_count"] == 3
    assert rec.details["retried"] is True
    assert rec.workflow_id == "wf_test07"


@pytest.mark.parametrize(
    "variable,expected_count",
    [
        ("AGE_GROUP", 2),
        ("IS_ELDERLY", 1),
        ("NONEXISTENT", 0),
    ],
)
def test_audit_trail_get_variable_history_counts(variable: str, expected_count: int) -> None:
    # Arrange
    trail = AuditTrail("wf_test08")
    trail.record("AGE_GROUP", "derivation_started", "coder")
    trail.record("IS_ELDERLY", "derivation_started", "coder")
    trail.record("AGE_GROUP", "approved", "orchestrator")

    # Act
    history = trail.get_variable_history(variable)

    # Assert
    assert len(history) == expected_count
