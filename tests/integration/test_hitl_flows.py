"""Integration tests for the HITL (approve/reject/override) API surface."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.api.workflow_manager import WorkflowManager
from src.audit.trail import AuditTrail
from src.domain.dag import DerivationDAG
from src.domain.enums import AuditAction, DerivationStatus
from src.domain.models import DerivationRule, OutputDType
from src.engine.pipeline_context import PipelineContext
from src.engine.pipeline_fsm import PipelineFSM
from src.persistence.database import init_db
from src.persistence.orm_models import FeedbackRow

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_AGE_GROUP_CODE = "df['age'].apply(lambda x: 'senior' if x >= 65 else ('minor' if x < 18 else 'adult'))"

_SOURCE_DF = pd.DataFrame(
    {
        "patient_id": ["P001", "P002", "P003"],
        "age": [72, 45, 15],
        "treatment_start": ["2024-01-01", "2024-02-01", "2024-03-01"],
        "treatment_end": ["2024-06-01", "2024-07-01", "2024-09-01"],
        "group": ["treatment", "placebo", "treatment"],
    }
)


def _make_ctx(workflow_id: str, tmp_path: Path) -> PipelineContext:
    """Build a minimal PipelineContext with a DAG + derived_df."""
    ctx = PipelineContext(
        workflow_id=workflow_id,
        audit_trail=AuditTrail(workflow_id),
        llm_base_url="http://localhost:8650/v1",
        output_dir=tmp_path / "output",
    )
    rules = [
        DerivationRule(
            variable="AGE_GROUP",
            source_columns=["age"],
            logic="senior/adult/minor by age",
            output_type=OutputDType.STR,
        )
    ]
    source_cols = {"patient_id", "age", "treatment_start", "treatment_end", "group"}
    ctx.dag = DerivationDAG(rules, source_cols)
    ctx.source_df = _SOURCE_DF.copy()
    ctx.derived_df = _SOURCE_DF.copy()

    node = ctx.dag.get_node("AGE_GROUP")
    node.status = DerivationStatus.APPROVED
    node.approved_code = _AGE_GROUP_CODE
    node.coder_code = _AGE_GROUP_CODE

    from src.domain.models import SourceConfig, SpecMetadata, SyntheticConfig, TransformationSpec

    ctx.spec = TransformationSpec(
        metadata=SpecMetadata(study="test_study", description="test", version="0.1", author="dev"),
        source=SourceConfig(format="csv", path="data/patients.csv", domains=["dm"], primary_key="patient_id"),
        derivations=rules,
        synthetic=SyntheticConfig(rows=10),
    )
    return ctx


async def _wire_hitl_ctx(
    manager: WorkflowManager,
    workflow_id: str,
    tmp_path: Path,
) -> asyncio.Event:
    """Register a fake in-HITL-gate workflow on the manager. Returns the approval event."""
    session_factory = await init_db()
    session = session_factory()  # async_sessionmaker returns AsyncSession
    ctx = _make_ctx(workflow_id, tmp_path)
    fsm = PipelineFSM(workflow_id, step_ids=["parse_spec", "human_review"])
    approval_event = asyncio.Event()
    ctx.step_outputs["human_review"] = {"_approval_event": approval_event}

    manager._contexts[workflow_id] = ctx  # type: ignore[attr-defined]
    manager._fsms[workflow_id] = fsm  # type: ignore[attr-defined]
    manager._sessions[workflow_id] = session  # type: ignore[attr-defined]
    manager._interpreters[workflow_id] = None  # type: ignore[index]
    manager._started_at[workflow_id] = "2024-01-01T00:00:00"  # type: ignore[attr-defined]
    return approval_event


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def client_and_manager(tmp_path: Path) -> AsyncGenerator[tuple[AsyncClient, WorkflowManager]]:
    """Test client + WorkflowManager pair (no lifespan)."""
    from src.api.app import create_app

    app = create_app()
    manager = WorkflowManager()
    app.state.workflow_manager = manager
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, manager
    await manager.cancel_active()


# ---------------------------------------------------------------------------
# Test 1 — reject sets rejection flag + writes feedback
# ---------------------------------------------------------------------------


async def test_reject_workflow_sets_flag_and_writes_feedback(
    client_and_manager: tuple[AsyncClient, WorkflowManager],
    tmp_path: Path,
) -> None:
    # Arrange
    client, manager = client_and_manager
    wf_id = "wf-reject-01"
    await _wire_hitl_ctx(manager, wf_id, tmp_path)

    # Act
    response = await client.post(f"/api/v1/workflows/{wf_id}/reject", json={"reason": "bad derivation"})

    # Assert HTTP
    assert response.status_code == 200

    # Assert rejection flag on context
    ctx = manager.get_context(wf_id)
    assert ctx is not None
    assert ctx.rejection_requested is True
    assert ctx.rejection_reason == "bad derivation"

    # Assert feedback row persisted
    session = manager._sessions.get(wf_id)  # type: ignore[attr-defined]
    if session is not None:
        result = await session.execute(select(FeedbackRow).where(FeedbackRow.action_taken == "rejected"))
        rows = list(result.scalars())
        assert len(rows) >= 1
        assert rows[0].feedback == "bad derivation"


# ---------------------------------------------------------------------------
# Test 2 — reject with empty reason returns 422
# ---------------------------------------------------------------------------


async def test_reject_with_empty_reason_returns_422(
    client_and_manager: tuple[AsyncClient, WorkflowManager],
    tmp_path: Path,
) -> None:
    # Arrange
    client, manager = client_and_manager
    wf_id = "wf-reject-empty"
    await _wire_hitl_ctx(manager, wf_id, tmp_path)

    # Act
    response = await client.post(f"/api/v1/workflows/{wf_id}/reject", json={"reason": ""})

    # Assert
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Test 3 — approve with per-variable payload writes feedback rows
# ---------------------------------------------------------------------------


async def test_approve_with_per_variable_payload_writes_feedback(
    client_and_manager: tuple[AsyncClient, WorkflowManager],
    tmp_path: Path,
) -> None:
    # Arrange
    client, manager = client_and_manager
    wf_id = "wf-approve-fb"
    await _wire_hitl_ctx(manager, wf_id, tmp_path)
    payload = {
        "variables": [{"variable": "AGE_GROUP", "approved": True, "note": "looks correct"}],
        "reason": "good run",
    }

    # Act
    response = await client.post(f"/api/v1/workflows/{wf_id}/approve", json=payload)

    # Assert HTTP
    assert response.status_code == 200

    # Assert feedback row written for AGE_GROUP
    session = manager._sessions.get(wf_id)  # type: ignore[attr-defined]
    if session is not None:
        result = await session.execute(select(FeedbackRow).where(FeedbackRow.variable == "AGE_GROUP"))
        rows = list(result.scalars())
        assert len(rows) >= 1
        assert rows[0].action_taken == "approved"


# ---------------------------------------------------------------------------
# Test 4 — approve with no body releases the gate (backwards compat)
# ---------------------------------------------------------------------------


async def test_approve_with_no_body_releases_gate(
    client_and_manager: tuple[AsyncClient, WorkflowManager],
    tmp_path: Path,
) -> None:
    # Arrange
    client, manager = client_and_manager
    wf_id = "wf-approve-nobo"
    event = await _wire_hitl_ctx(manager, wf_id, tmp_path)

    # Act
    response = await client.post(f"/api/v1/workflows/{wf_id}/approve")

    # Assert
    assert response.status_code == 200
    assert event.is_set()  # gate released


# ---------------------------------------------------------------------------
# Test 5 — override rewrites approved_code and writes HUMAN_OVERRIDE audit
# ---------------------------------------------------------------------------


async def test_override_variable_rewrites_approved_code(
    client_and_manager: tuple[AsyncClient, WorkflowManager],
    tmp_path: Path,
) -> None:
    # Arrange
    client, manager = client_and_manager
    wf_id = "wf-override-01"
    await _wire_hitl_ctx(manager, wf_id, tmp_path)
    new_code = "df['age'].apply(lambda x: 'senior' if x >= 60 else 'other')"
    payload = {"new_code": new_code, "reason": "adjusted threshold"}

    # Act
    response = await client.post(f"/api/v1/workflows/{wf_id}/variables/AGE_GROUP/override", json=payload)

    # Assert HTTP
    assert response.status_code == 200
    body: dict[str, object] = response.json()
    assert body["variable"] == "AGE_GROUP"

    # Assert DAG node updated
    ctx = manager.get_context(wf_id)
    assert ctx is not None
    assert ctx.dag is not None
    assert ctx.dag.get_node("AGE_GROUP").approved_code == new_code

    # Assert audit record
    override_records = [r for r in ctx.audit_trail.records if r.action == AuditAction.HUMAN_OVERRIDE]
    assert len(override_records) == 1
    assert override_records[0].variable == "AGE_GROUP"


# ---------------------------------------------------------------------------
# Test 6 — override with invalid code returns 400, original code preserved
# ---------------------------------------------------------------------------


async def test_override_variable_with_invalid_code_returns_400(
    client_and_manager: tuple[AsyncClient, WorkflowManager],
    tmp_path: Path,
) -> None:
    # Arrange
    client, manager = client_and_manager
    wf_id = "wf-override-bad"
    await _wire_hitl_ctx(manager, wf_id, tmp_path)
    original_code = _AGE_GROUP_CODE
    broken_code = "df['AGE_GROUP'] = this_does_not_exist(df)"
    payload = {"new_code": broken_code, "reason": "test invalid"}

    # Act
    response = await client.post(f"/api/v1/workflows/{wf_id}/variables/AGE_GROUP/override", json=payload)

    # Assert 400
    assert response.status_code == 400

    # Assert original code preserved
    ctx = manager.get_context(wf_id)
    assert ctx is not None
    assert ctx.dag is not None
    assert ctx.dag.get_node("AGE_GROUP").approved_code == original_code


# ---------------------------------------------------------------------------
# Test 7 — override for unknown variable returns 404
# ---------------------------------------------------------------------------


async def test_override_unknown_variable_returns_404(
    client_and_manager: tuple[AsyncClient, WorkflowManager],
    tmp_path: Path,
) -> None:
    # Arrange
    client, manager = client_and_manager
    wf_id = "wf-override-404"
    await _wire_hitl_ctx(manager, wf_id, tmp_path)

    # Act
    response = await client.post(
        f"/api/v1/workflows/{wf_id}/variables/NONEXISTENT_VAR/override",
        json={"new_code": "df['X'] = 1", "reason": "test"},
    )

    # Assert
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test 8 — reject on workflow not awaiting approval returns 409
# ---------------------------------------------------------------------------


async def test_reject_on_workflow_not_at_gate_returns_409(
    client_and_manager: tuple[AsyncClient, WorkflowManager],
    tmp_path: Path,
) -> None:
    # Arrange — register a context with no approval event (gate not active)
    client, manager = client_and_manager
    wf_id = "wf-reject-409"
    ctx = _make_ctx(wf_id, tmp_path)
    fsm = PipelineFSM(wf_id, step_ids=["parse_spec"])
    manager._contexts[wf_id] = ctx  # type: ignore[attr-defined]
    manager._fsms[wf_id] = fsm  # type: ignore[attr-defined]
    manager._interpreters[wf_id] = None  # type: ignore[index]
    # No step_outputs with _approval_event — get_approval_event returns None

    # Act
    response = await client.post(f"/api/v1/workflows/{wf_id}/reject", json={"reason": "too late"})

    # Assert
    assert response.status_code == 409
