"""Unit tests for step executors — validation and error paths.

Agent execution tests (happy paths requiring LLM calls) are deferred to Phase 14.4
integration tests that use PydanticAI's TestModel/FunctionModel.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.enums import AuditAction
from src.domain.exceptions import WorkflowRejectedError
from src.domain.pipeline_models import StepDefinition, StepType
from src.engine.pipeline_context import PipelineContext
from src.engine.step_executors import (
    STEP_EXECUTOR_REGISTRY,
    AgentStepExecutor,
    BuiltinStepExecutor,
    GatherStepExecutor,
    HITLGateStepExecutor,
    ParallelMapStepExecutor,
)


@pytest.fixture
def mock_ctx() -> PipelineContext:
    """Minimal PipelineContext for testing executor validation."""
    from src.audit.trail import AuditTrail

    return PipelineContext(
        workflow_id="test-wf",
        audit_trail=AuditTrail("test-wf"),
        llm_base_url="http://localhost:8650/v1",
    )


async def test_agent_executor_missing_agent_field_raises_value_error(mock_ctx: PipelineContext) -> None:
    """AgentStepExecutor raises ValueError if step has no agent field."""
    # Arrange
    step = StepDefinition(id="bad", type=StepType.AGENT)
    executor = AgentStepExecutor()

    # Act & Assert
    with pytest.raises(ValueError, match="no 'agent' field"):
        await executor.execute(step, mock_ctx)


async def test_builtin_executor_missing_builtin_field_raises_value_error(mock_ctx: PipelineContext) -> None:
    """BuiltinStepExecutor raises ValueError if step has no builtin field."""
    # Arrange
    step = StepDefinition(id="bad", type=StepType.BUILTIN)
    executor = BuiltinStepExecutor()

    # Act & Assert
    with pytest.raises(ValueError, match="no 'builtin' field"):
        await executor.execute(step, mock_ctx)


async def test_builtin_executor_unknown_builtin_raises_value_error(mock_ctx: PipelineContext) -> None:
    """BuiltinStepExecutor raises ValueError for unregistered builtin name."""
    # Arrange
    step = StepDefinition(id="bad", type=StepType.BUILTIN, builtin="nonexistent")
    executor = BuiltinStepExecutor()

    # Act & Assert
    with pytest.raises(ValueError, match="Unknown builtin 'nonexistent'"):
        await executor.execute(step, mock_ctx)


async def test_gather_executor_missing_agents_raises_value_error(mock_ctx: PipelineContext) -> None:
    """GatherStepExecutor raises ValueError if step has no agents list."""
    # Arrange
    step = StepDefinition(id="bad", type=StepType.GATHER)
    executor = GatherStepExecutor()

    # Act & Assert
    with pytest.raises(ValueError, match="no 'agents' list"):
        await executor.execute(step, mock_ctx)


async def test_parallel_map_unsupported_over_raises_value_error(mock_ctx: PipelineContext) -> None:
    """ParallelMapStepExecutor only supports over='dag_layers'."""
    # Arrange
    step = StepDefinition(id="bad", type=StepType.PARALLEL_MAP, over="something_else")
    executor = ParallelMapStepExecutor()

    # Act & Assert
    with pytest.raises(ValueError, match="only supports over='dag_layers'"):
        await executor.execute(step, mock_ctx)


def test_step_executor_registry_has_all_step_types() -> None:
    """STEP_EXECUTOR_REGISTRY covers every StepType enum member."""
    # Act & Assert
    for step_type in StepType:
        assert step_type in STEP_EXECUTOR_REGISTRY, f"Missing executor for {step_type}"


async def test_agent_step_executor_records_step_started_with_agent_name(mock_ctx: PipelineContext) -> None:
    """STEP_STARTED audit record uses the step's agent name, not orchestrator."""
    # Arrange
    step = StepDefinition(id="spec_interpreter", type=StepType.AGENT, agent="spec_interpreter")
    executor = AgentStepExecutor()

    mock_agent = MagicMock()
    mock_result = MagicMock()
    mock_result.output = "parsed spec"
    mock_agent.run = AsyncMock(return_value=mock_result)

    with (
        patch("src.agents.factory.load_agent", return_value=mock_agent),
        patch("src.config.llm_gateway.create_llm", return_value=MagicMock()),
        patch("src.config.settings.get_settings", return_value=MagicMock(agent_config_dir="agents")),
        patch("src.engine.step_executors.build_agent_deps_and_prompt", return_value=(MagicMock(), "prompt")),
    ):
        # Act
        await executor.execute(step, mock_ctx)

    # Assert — STEP_STARTED record carries the step's agent name, not "orchestrator"
    step_started_records = [r for r in mock_ctx.audit_trail.records if r.action == AuditAction.STEP_STARTED]
    assert len(step_started_records) == 1
    assert step_started_records[0].agent == "spec_interpreter"
    assert step_started_records[0].agent != "orchestrator"


async def test_hitl_gate_with_rejection_flag_raises_workflow_rejected_error(mock_ctx: PipelineContext) -> None:
    """HITLGateStepExecutor raises WorkflowRejectedError and records HUMAN_REJECTED when flag is set."""
    # Arrange
    step = StepDefinition(id="review_gate", type=StepType.HITL_GATE)
    mock_ctx.rejection_requested = True
    mock_ctx.rejection_reason = "bad derivation"
    executor = HITLGateStepExecutor()

    # Act — start executor as a task, then set the event once it registers in ctx
    task = asyncio.create_task(executor.execute(step, mock_ctx))
    await asyncio.sleep(0)  # yield to let executor reach approval_event.wait()
    event = mock_ctx.step_outputs["review_gate"]["_approval_event"]
    event.set()

    # Assert
    with pytest.raises(WorkflowRejectedError, match="bad derivation"):
        await task

    rejected_records = [r for r in mock_ctx.audit_trail.records if r.action == AuditAction.HUMAN_REJECTED]
    assert len(rejected_records) == 1
    assert rejected_records[0].details == {"gate": "review_gate", "reason": "bad derivation"}

    approved_records = [r for r in mock_ctx.audit_trail.records if r.action == AuditAction.HUMAN_APPROVED]
    assert len(approved_records) == 0

    # STEP_STARTED is always emitted; STEP_COMPLETED is NOT emitted on the reject path
    # because the executor raises before reaching it.
    started_records = [r for r in mock_ctx.audit_trail.records if r.action == AuditAction.STEP_STARTED]
    completed_records = [r for r in mock_ctx.audit_trail.records if r.action == AuditAction.STEP_COMPLETED]
    assert len(started_records) == 1
    assert len(completed_records) == 0


async def test_hitl_gate_without_rejection_flag_records_human_approved(mock_ctx: PipelineContext) -> None:
    """HITLGateStepExecutor records HUMAN_APPROVED and does not raise when rejection flag is not set."""
    # Arrange
    step = StepDefinition(id="review_gate", type=StepType.HITL_GATE)
    mock_ctx.rejection_requested = False
    # Simulate workflow_hitl.approve_with_feedback_impl having populated these before event.set():
    mock_ctx.approval_reason = "looks good overall"
    mock_ctx.approval_approved_vars = ["AGE_GROUP", "TREATMENT_DURATION"]
    mock_ctx.approval_rejected_vars = ["RISK_SCORE"]
    executor = HITLGateStepExecutor()

    # Act — start executor as a task, then set the event once it registers in ctx
    task = asyncio.create_task(executor.execute(step, mock_ctx))
    await asyncio.sleep(0)  # yield to let executor reach approval_event.wait()
    event = mock_ctx.step_outputs["review_gate"]["_approval_event"]
    event.set()
    await task

    # Assert — HUMAN_APPROVED carries per-variable decisions + reason
    approved_records = [r for r in mock_ctx.audit_trail.records if r.action == AuditAction.HUMAN_APPROVED]
    assert len(approved_records) == 1
    details = approved_records[0].details
    assert details["gate"] == "review_gate"
    assert details["reason"] == "looks good overall"
    assert details["approved"] == "AGE_GROUP, TREATMENT_DURATION"
    assert details["rejected"] == "RISK_SCORE"
    assert details["approved_count"] == 2
    assert details["rejected_count"] == 1

    rejected_records = [r for r in mock_ctx.audit_trail.records if r.action == AuditAction.HUMAN_REJECTED]
    assert len(rejected_records) == 0

    # Approve path emits both STEP_STARTED and STEP_COMPLETED for symmetry with other step executors
    started_records = [r for r in mock_ctx.audit_trail.records if r.action == AuditAction.STEP_STARTED]
    completed_records = [r for r in mock_ctx.audit_trail.records if r.action == AuditAction.STEP_COMPLETED]
    assert len(started_records) == 1
    assert len(completed_records) == 1


async def test_hitl_gate_without_approval_payload_uses_legacy_fallback(mock_ctx: PipelineContext) -> None:
    """When /approve is called with no body (backwards compat), the approval lists are empty.

    HUMAN_APPROVED details show the "(legacy no-body approve — all variables)" fallback.
    """
    # Arrange
    step = StepDefinition(id="review_gate", type=StepType.HITL_GATE)
    # mock_ctx.approval_reason / approval_approved_vars / approval_rejected_vars all default-empty
    executor = HITLGateStepExecutor()

    # Act
    task = asyncio.create_task(executor.execute(step, mock_ctx))
    await asyncio.sleep(0)
    event = mock_ctx.step_outputs["review_gate"]["_approval_event"]
    event.set()
    await task

    # Assert — legacy fallback text appears in details
    approved_records = [r for r in mock_ctx.audit_trail.records if r.action == AuditAction.HUMAN_APPROVED]
    assert len(approved_records) == 1
    details = approved_records[0].details
    assert details["reason"] == "(no reason provided)"
    assert details["approved"] == "(legacy no-body approve — all variables)"
    assert details["rejected"] == "(none)"
    assert details["approved_count"] == 0
    assert details["rejected_count"] == 0
