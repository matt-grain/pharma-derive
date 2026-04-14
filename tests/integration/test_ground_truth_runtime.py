"""Integration tests for the compare_ground_truth builtin and the ground_truth API endpoint."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

import pandas as pd
import pyreadstat  # type: ignore[import-untyped]
import pytest
from httpx import ASGITransport, AsyncClient

from src.audit.trail import AuditTrail
from src.domain.enums import QCVerdict
from src.domain.ground_truth import GroundTruthReport  # noqa: TC001 — used at runtime in type annotation
from src.domain.models import (
    DerivationRule,
    GroundTruthConfig,
    OutputDType,
    SourceConfig,
    SpecMetadata,
    SyntheticConfig,
    ToleranceConfig,
    TransformationSpec,
    ValidationConfig,
)
from src.domain.pipeline_models import StepDefinition, StepType
from src.engine.pipeline_context import PipelineContext
from src.engine.step_builtins import BUILTIN_REGISTRY

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


_GROUND_TRUTH_XPT = Path("data/adam/cdiscpilot01/adsl.xpt")

_COMPARE_STEP = StepDefinition(
    id="compare_ground_truth",
    type=StepType.BUILTIN,
    builtin="compare_ground_truth",
    description="Compare derived output against reference ADaM",
)


def _make_adsl_spec(primary_key: str = "USUBJID") -> TransformationSpec:
    """Build a TransformationSpec pointing at the real ADSL ground-truth XPT."""
    return TransformationSpec(
        metadata=SpecMetadata(study="cdiscpilot01", description="test", version="1.0", author="test"),
        source=SourceConfig(
            format="xpt",
            path="data/sdtm/cdiscpilot01",
            domains=["dm"],
            primary_key=primary_key,
        ),
        synthetic=SyntheticConfig(rows=5),
        validation=ValidationConfig(
            ground_truth=GroundTruthConfig(
                path=str(_GROUND_TRUTH_XPT),
                format="xpt",
                key=primary_key,
            ),
            tolerance=ToleranceConfig(numeric=0.01),
        ),
        derivations=[
            DerivationRule(
                variable="AGEGR1",
                source_columns=["AGE"],
                logic="Age group",
                output_type=OutputDType.STR,
                allowed_values=["<65", "65-80", ">80"],
            ),
        ],
    )


def _build_ctx_with_derived_agegr1(agegr1_series: pd.Series[str]) -> PipelineContext:
    """Build a PipelineContext with derived_df populated from the ground-truth AGEGR1 values."""
    gt_df = cast("pd.DataFrame", pyreadstat.read_xport(str(_GROUND_TRUTH_XPT))[0])  # type: ignore[no-untyped-call]
    derived_df: pd.DataFrame = gt_df[["USUBJID"]].copy()
    derived_df["AGEGR1"] = agegr1_series.to_numpy()

    ctx = PipelineContext(
        workflow_id="gt-test-01",
        audit_trail=AuditTrail("gt-test-01"),
        llm_base_url="http://localhost:8650/v1",
    )
    ctx.spec = _make_adsl_spec()
    ctx.derived_df = derived_df
    return ctx


# ---------------------------------------------------------------------------
# Test 1 — happy path: derived matches ground truth
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _GROUND_TRUTH_XPT.exists(), reason="ADSL XPT not available")
async def test_ground_truth_builtin_compares_derived_to_reference_xpt() -> None:
    """Builtin compares AGEGR1 correctly against the real ADSL XPT and reports a MATCH."""
    # Arrange — use the AGEGR1 column from the reference XPT itself as the derived series
    gt_df = cast("pd.DataFrame", pyreadstat.read_xport(str(_GROUND_TRUTH_XPT))[0])  # type: ignore[no-untyped-call]
    ctx = _build_ctx_with_derived_agegr1(gt_df["AGEGR1"].astype(str))

    # Act
    await BUILTIN_REGISTRY["compare_ground_truth"](_COMPARE_STEP, ctx)

    # Assert
    assert ctx.ground_truth_report is not None
    report: GroundTruthReport = ctx.ground_truth_report
    assert report.matched_variables >= 1
    agegr1_result = next((r for r in report.results if r.variable == "AGEGR1"), None)
    assert agegr1_result is not None
    assert agegr1_result.verdict == QCVerdict.MATCH
    assert agegr1_result.error is None


# ---------------------------------------------------------------------------
# Test 2 — variable not present in ground truth → error field set, no crash
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _GROUND_TRUTH_XPT.exists(), reason="ADSL XPT not available")
async def test_ground_truth_skips_variables_not_in_reference() -> None:
    """Variable absent from ground-truth XPT produces error field, not a crash."""
    # Arrange — spec with a phantom variable that doesn't exist in adsl.xpt
    gt_df = cast("pd.DataFrame", pyreadstat.read_xport(str(_GROUND_TRUTH_XPT))[0])  # type: ignore[no-untyped-call]
    derived_df: pd.DataFrame = gt_df[["USUBJID"]].copy()
    derived_df["PHANTOM_VAR"] = "X"

    phantom_spec = TransformationSpec(
        metadata=SpecMetadata(study="cdiscpilot01", description="test", version="1.0", author="test"),
        source=SourceConfig(format="xpt", path="data/sdtm/cdiscpilot01", domains=["dm"], primary_key="USUBJID"),
        synthetic=SyntheticConfig(rows=5),
        validation=ValidationConfig(
            ground_truth=GroundTruthConfig(path=str(_GROUND_TRUTH_XPT), format="xpt", key="USUBJID"),
            tolerance=ToleranceConfig(numeric=0.0),
        ),
        derivations=[
            DerivationRule(
                variable="PHANTOM_VAR",
                source_columns=["USUBJID"],
                logic="Phantom variable for testing",
                output_type=OutputDType.STR,
            ),
        ],
    )
    ctx = PipelineContext(
        workflow_id="gt-phantom-01",
        audit_trail=AuditTrail("gt-phantom-01"),
        llm_base_url="http://localhost:8650/v1",
    )
    ctx.spec = phantom_spec
    ctx.derived_df = derived_df

    # Act — must NOT raise
    await BUILTIN_REGISTRY["compare_ground_truth"](_COMPARE_STEP, ctx)

    # Assert
    assert ctx.ground_truth_report is not None
    phantom_result = next((r for r in ctx.ground_truth_report.results if r.variable == "PHANTOM_VAR"), None)
    assert phantom_result is not None
    assert phantom_result.verdict == QCVerdict.MISMATCH
    assert phantom_result.error is not None


# ---------------------------------------------------------------------------
# Test 3 — endpoint returns 200 + report JSON after workflow ran
# ---------------------------------------------------------------------------


@pytest.fixture
async def client_and_manager() -> AsyncGenerator[tuple[AsyncClient, object]]:
    """Test client + WorkflowManager with a pre-wired workflow context."""
    from src.api.app import create_app
    from src.api.workflow_manager import WorkflowManager

    app = create_app()
    manager = WorkflowManager()
    app.state.workflow_manager = manager
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, manager
    await manager.cancel_active()


@pytest.mark.skipif(not _GROUND_TRUTH_XPT.exists(), reason="ADSL XPT not available")
async def test_ground_truth_endpoint_returns_report(
    client_and_manager: tuple[AsyncClient, object],
) -> None:
    """GET /workflows/{id}/ground_truth returns 200 + JSON report when the step has run."""
    # Arrange
    from src.api.workflow_manager import WorkflowManager
    from src.engine.pipeline_fsm import PipelineFSM

    client, manager = client_and_manager
    assert isinstance(manager, WorkflowManager)

    wf_id = "gt-endpoint-01"
    gt_df = cast("pd.DataFrame", pyreadstat.read_xport(str(_GROUND_TRUTH_XPT))[0])  # type: ignore[no-untyped-call]
    ctx = PipelineContext(
        workflow_id=wf_id,
        audit_trail=AuditTrail(wf_id),
        llm_base_url="http://localhost:8650/v1",
    )
    ctx.spec = _make_adsl_spec()
    derived_df: pd.DataFrame = gt_df[["USUBJID"]].copy()
    derived_df["AGEGR1"] = gt_df["AGEGR1"].astype(str).to_numpy()
    ctx.derived_df = derived_df

    # Run the builtin to populate ground_truth_report
    await BUILTIN_REGISTRY["compare_ground_truth"](_COMPARE_STEP, ctx)
    assert ctx.ground_truth_report is not None

    # Wire context into manager — interpreter must be non-None for the endpoint to return data
    from src.domain.pipeline_models import PipelineDefinition
    from src.engine.pipeline_interpreter import PipelineInterpreter

    fsm = PipelineFSM(wf_id, step_ids=["parse_spec", "compare_ground_truth"])
    mock_pipeline = PipelineDefinition(name="test", steps=[])
    mock_interpreter = PipelineInterpreter(mock_pipeline, ctx)
    manager._contexts[wf_id] = ctx  # type: ignore[attr-defined]
    manager._fsms[wf_id] = fsm  # type: ignore[attr-defined]
    manager._interpreters[wf_id] = mock_interpreter  # type: ignore[attr-defined]
    manager._started_at[wf_id] = "2024-01-01T00:00:00"  # type: ignore[attr-defined]

    # Act
    response = await client.get(f"/api/v1/workflows/{wf_id}/ground_truth")

    # Assert
    assert response.status_code == 200
    body: dict[str, object] = response.json()
    assert isinstance(body["total_variables"], int)
    assert body["total_variables"] >= 1
    results: list[object] = list(cast("list[object]", body["results"]))
    assert len(results) >= 1


# ---------------------------------------------------------------------------
# Test 4 — endpoint returns 404 when step has not run
# ---------------------------------------------------------------------------


async def test_ground_truth_endpoint_404_when_not_run(
    client_and_manager: tuple[AsyncClient, object],
) -> None:
    """GET /workflows/{id}/ground_truth returns 404 when compare_ground_truth hasn't fired."""
    # Arrange
    from src.api.workflow_manager import WorkflowManager
    from src.engine.pipeline_fsm import PipelineFSM

    client, manager = client_and_manager
    assert isinstance(manager, WorkflowManager)

    wf_id = "gt-no-report-01"
    ctx = PipelineContext(
        workflow_id=wf_id,
        audit_trail=AuditTrail(wf_id),
        llm_base_url="http://localhost:8650/v1",
    )
    # ground_truth_report is None (step never ran) — interpreter with no completed steps
    from src.domain.pipeline_models import PipelineDefinition
    from src.engine.pipeline_interpreter import PipelineInterpreter

    fsm = PipelineFSM(wf_id, step_ids=["parse_spec"])
    mock_pipeline = PipelineDefinition(name="test", steps=[])
    mock_interpreter = PipelineInterpreter(mock_pipeline, ctx)
    manager._contexts[wf_id] = ctx  # type: ignore[attr-defined]
    manager._fsms[wf_id] = fsm  # type: ignore[attr-defined]
    manager._interpreters[wf_id] = mock_interpreter  # type: ignore[attr-defined]
    manager._started_at[wf_id] = "2024-01-01T00:00:00"  # type: ignore[attr-defined]

    # Act
    response = await client.get(f"/api/v1/workflows/{wf_id}/ground_truth")

    # Assert
    assert response.status_code == 404
    assert "Ground truth check has not yet run" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Test 5 — graceful skip when no ground_truth configured in spec
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Test 6 — endpoint 404 "not yet run": interpreter exists but step not completed
# ---------------------------------------------------------------------------


async def test_ground_truth_endpoint_returns_404_with_premature_message_when_step_not_run(
    client_and_manager: tuple[AsyncClient, object],
) -> None:
    """GET /ground_truth returns 404 with 'not yet run' message when ground_truth_check hasn't completed."""
    # Arrange — interpreter present but no completed steps; report is None
    from src.api.workflow_manager import WorkflowManager
    from src.domain.pipeline_models import PipelineDefinition
    from src.engine.pipeline_fsm import PipelineFSM
    from src.engine.pipeline_interpreter import PipelineInterpreter

    client, manager = client_and_manager
    assert isinstance(manager, WorkflowManager)

    wf_id = "gt-premature-01"
    ctx = PipelineContext(
        workflow_id=wf_id,
        audit_trail=AuditTrail(wf_id),
        llm_base_url="http://localhost:8650/v1",
    )
    # ground_truth_report stays None — step never ran
    fsm = PipelineFSM(wf_id, step_ids=["parse_spec"])
    mock_pipeline = PipelineDefinition(name="test", steps=[])
    interpreter = PipelineInterpreter(mock_pipeline, ctx)
    # No steps have been appended to interpreter._completed_steps
    manager._contexts[wf_id] = ctx  # type: ignore[attr-defined]
    manager._fsms[wf_id] = fsm  # type: ignore[attr-defined]
    manager._interpreters[wf_id] = interpreter  # type: ignore[attr-defined]
    manager._started_at[wf_id] = "2024-01-01T00:00:00"  # type: ignore[attr-defined]

    # Act
    response = await client.get(f"/api/v1/workflows/{wf_id}/ground_truth")

    # Assert
    assert response.status_code == 404
    assert response.json()["detail"] == "Ground truth check has not yet run for this workflow"


# ---------------------------------------------------------------------------
# Test 7 — endpoint 404 "no path": ground_truth_check completed but spec lacks path
# ---------------------------------------------------------------------------


async def test_ground_truth_endpoint_returns_404_with_no_path_message_when_spec_lacks_ground_truth_path(
    client_and_manager: tuple[AsyncClient, object],
) -> None:
    """GET /ground_truth returns 404 with 'no path' message when step ran but spec has no ground_truth_path."""
    # Arrange — interpreter has ground_truth_check in completed steps; report is still None
    from src.api.workflow_manager import WorkflowManager
    from src.domain.pipeline_models import PipelineDefinition, StepDefinition, StepType
    from src.engine.pipeline_fsm import PipelineFSM
    from src.engine.pipeline_interpreter import PipelineInterpreter

    client, manager = client_and_manager
    assert isinstance(manager, WorkflowManager)

    wf_id = "gt-no-path-01"
    ctx = PipelineContext(
        workflow_id=wf_id,
        audit_trail=AuditTrail(wf_id),
        llm_base_url="http://localhost:8650/v1",
    )
    # ground_truth_report is None because spec has no ground_truth_path (builtin short-circuits)
    gt_check_step = StepDefinition(
        id="ground_truth_check",
        type=StepType.BUILTIN,
        builtin="compare_ground_truth",
    )
    mock_pipeline = PipelineDefinition(name="test", steps=[gt_check_step])
    interpreter = PipelineInterpreter(mock_pipeline, ctx)
    # Simulate that ground_truth_check ran (completed) but produced no report
    interpreter._completed_steps.append(gt_check_step)  # type: ignore[attr-defined]

    fsm = PipelineFSM(wf_id, step_ids=["ground_truth_check"])
    manager._contexts[wf_id] = ctx  # type: ignore[attr-defined]
    manager._fsms[wf_id] = fsm  # type: ignore[attr-defined]
    manager._interpreters[wf_id] = interpreter  # type: ignore[attr-defined]
    manager._started_at[wf_id] = "2024-01-01T00:00:00"  # type: ignore[attr-defined]

    # Act
    response = await client.get(f"/api/v1/workflows/{wf_id}/ground_truth")

    # Assert
    assert response.status_code == 404
    assert response.json()["detail"] == "No ground truth report available — spec has no ground_truth_path declared"


# ---------------------------------------------------------------------------
# Test 5 — graceful skip when no ground_truth configured in spec
# ---------------------------------------------------------------------------


async def test_ground_truth_builtin_skips_gracefully_when_no_config() -> None:
    """Builtin returns early without error when spec has no validation.ground_truth."""
    # Arrange
    ctx = PipelineContext(
        workflow_id="gt-skip-01",
        audit_trail=AuditTrail("gt-skip-01"),
        llm_base_url="http://localhost:8650/v1",
    )
    ctx.spec = TransformationSpec(
        metadata=SpecMetadata(study="express_test", description="test", version="1.0", author="test"),
        source=SourceConfig(format="csv", path="data/patients.csv", domains=["dm"], primary_key="USUBJID"),
        synthetic=SyntheticConfig(rows=5),
        validation=ValidationConfig(ground_truth=None),  # no ground truth
        derivations=[
            DerivationRule(
                variable="AGE_GROUP", source_columns=["AGE"], logic="age group", output_type=OutputDType.STR
            ),
        ],
    )
    ctx.derived_df = pd.DataFrame({"USUBJID": ["S001"], "AGE_GROUP": ["<65"]})

    # Act — must NOT raise, must NOT set ground_truth_report
    await BUILTIN_REGISTRY["compare_ground_truth"](_COMPARE_STEP, ctx)

    # Assert
    assert ctx.ground_truth_report is None
