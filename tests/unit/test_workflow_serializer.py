"""Tests for src/api/workflow_serializer.py — serialization round-trips."""

from __future__ import annotations

import json

from src.api.workflow_serializer import HistoricState, serialize_ctx
from src.audit.trail import AuditTrail
from src.domain.enums import WorkflowStep
from src.engine.pipeline_context import PipelineContext


def _make_ctx(workflow_id: str = "wf-test") -> PipelineContext:
    """Build a minimal PipelineContext with source_column_domains populated."""
    ctx = PipelineContext(
        workflow_id=workflow_id,
        audit_trail=AuditTrail(workflow_id),
        llm_base_url="http://localhost",
    )
    ctx.source_column_domains = {"AAGE": "DM", "SEX": "DM", "RACE": "DM"}
    return ctx


def test_serialize_ctx_includes_source_column_domains() -> None:
    """serialize_ctx must include source_column_domains in the JSON payload."""
    # Arrange
    ctx = _make_ctx()

    # Act
    payload = json.loads(serialize_ctx(ctx, WorkflowStep.COMPLETED.value))

    # Assert
    assert "source_column_domains" in payload
    assert payload["source_column_domains"] == {"AAGE": "DM", "SEX": "DM", "RACE": "DM"}


def test_historic_state_round_trip_preserves_source_column_domains() -> None:
    """Serialize then deserialize: source_column_domains survives the round-trip."""
    # Arrange
    ctx = _make_ctx("wf-roundtrip")

    # Act — serialize, then reconstruct via HistoricState
    state_json = serialize_ctx(ctx, WorkflowStep.COMPLETED.value)
    hist = HistoricState("wf-roundtrip", WorkflowStep.COMPLETED.value, state_json)

    # Assert
    assert hist.source_column_domains == {"AAGE": "DM", "SEX": "DM", "RACE": "DM"}


def test_historic_state_missing_source_column_domains_defaults_to_empty_dict() -> None:
    """Rows written before this field was added must load without error (backward compat)."""
    # Arrange — old-format state_json without source_column_domains
    old_state = json.dumps(
        {
            "workflow_id": "wf-old",
            "status": "completed",
            "study": "CDISCPILOT01",
            "derived_variables": [],
            "errors": [],
            "dag_nodes": {},
            "started_at": None,
            "completed_at": None,
        }
    )

    # Act
    hist = HistoricState("wf-old", "completed", old_state)

    # Assert — graceful fallback, no KeyError
    assert hist.source_column_domains == {}


def test_serialize_ctx_dag_nodes_include_source_columns() -> None:
    """When a DAG exists, each node's source_columns list is persisted in state_json."""
    from src.domain.dag import DerivationDAG
    from src.domain.enums import OutputDType
    from src.domain.models import DerivationRule

    # Arrange
    ctx = _make_ctx("wf-dag-cols")
    rule = DerivationRule(
        variable="AAGE",
        source_columns=["AGE"],
        logic="df['AGE']",
        output_type=OutputDType.INT,
    )
    ctx.dag = DerivationDAG([rule], source_columns={"AGE"})

    # Act
    payload = json.loads(serialize_ctx(ctx, WorkflowStep.COMPLETED.value))

    # Assert
    assert "source_columns" in payload["dag_nodes"]["AAGE"]
    assert payload["dag_nodes"]["AAGE"]["source_columns"] == ["AGE"]
