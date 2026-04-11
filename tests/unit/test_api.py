"""Tests for the FastAPI REST API."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient

from src.api.workflow_manager import WorkflowManager

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    """Create test client for the FastAPI app with lifespan executed."""
    from src.api.app import create_app

    app = create_app()
    manager = WorkflowManager()
    app.state.workflow_manager = manager
    transport = ASGITransport(app=app)  # type: ignore[arg-type]  # httpx transport typing
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await manager.cancel_active()


async def test_health_check_returns_ok(client: AsyncClient) -> None:
    # Act
    response = await client.get("/health")

    # Assert
    assert response.status_code == 200
    body: dict[str, object] = response.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"
    assert body["workflows_in_progress"] == 0


async def test_list_specs_returns_available_specs(client: AsyncClient) -> None:
    # Act
    response = await client.get("/api/v1/specs/")

    # Assert
    assert response.status_code == 200
    items: list[dict[str, object]] = response.json()
    assert isinstance(items, list)
    # specs/ directory has at least simple_mock.yaml and adsl_cdiscpilot01.yaml
    assert len(items) >= 1
    first = items[0]
    assert "filename" in first
    assert "study" in first
    assert "derivation_count" in first


async def test_start_workflow_returns_202(client: AsyncClient) -> None:
    # Arrange — simple_mock.yaml is a valid spec that doesn't need LLM for the 202
    payload = {"spec_path": "specs/simple_mock.yaml"}

    # Act
    response = await client.post("/api/v1/workflows/", json=payload)

    # Assert — 202 is returned before the background task runs
    assert response.status_code == 202
    body: dict[str, object] = response.json()
    assert "workflow_id" in body
    assert body["status"] == "running"


async def test_get_workflow_status_unknown_id_returns_404(client: AsyncClient) -> None:
    # Act
    response = await client.get("/api/v1/workflows/nonexistent-id-xyz")

    # Assert
    assert response.status_code == 404
    detail: str = response.json()["detail"]
    assert "not found" in detail.lower()


async def test_get_result_while_running_returns_409(client: AsyncClient) -> None:
    # Arrange — start a workflow (background task won't complete during this test)
    start_response = await client.post(
        "/api/v1/workflows/",
        json={"spec_path": "specs/simple_mock.yaml"},
    )
    assert start_response.status_code == 202
    workflow_id: str = start_response.json()["workflow_id"]

    # Act — immediately request result while task is still running
    result_response = await client.get(f"/api/v1/workflows/{workflow_id}/result")

    # Assert — 409 because still running
    assert result_response.status_code == 409
    detail: str = result_response.json()["detail"]
    assert "running" in detail.lower()


async def test_list_workflows_returns_array(client: AsyncClient) -> None:
    # Act
    response = await client.get("/api/v1/workflows/")

    # Assert
    assert response.status_code == 200
    body: list[object] = response.json()
    assert isinstance(body, list)


async def test_approve_nonexistent_workflow_returns_404(client: AsyncClient) -> None:
    # Act
    response = await client.post("/api/v1/workflows/nonexistent/approve")

    # Assert
    assert response.status_code == 404
    detail: str = response.json()["detail"]
    assert "not found" in detail.lower()


async def test_delete_nonexistent_workflow_returns_404(client: AsyncClient) -> None:
    # Act
    response = await client.delete("/api/v1/workflows/nonexistent-delete-id")

    # Assert
    assert response.status_code == 404
    detail: str = response.json()["detail"]
    assert "not found" in detail.lower()


async def test_get_data_preview_unknown_workflow_returns_404(client: AsyncClient) -> None:
    """GET /data on unknown workflow returns 404."""
    # Act
    response = await client.get("/api/v1/workflows/nonexistent/data")

    # Assert
    assert response.status_code == 404
    detail: str = response.json()["detail"]
    assert "not found" in detail.lower()


async def test_get_data_preview_completed_workflow_returns_columns_and_rows(
    client: AsyncClient,
    tmp_path: Path,
) -> None:
    """GET /data on a completed workflow returns source + derived preview."""
    # Arrange — write a small ADaM CSV to the output dir and register the workflow
    workflow_id = "test-preview-wf"
    adam_df = pd.DataFrame(
        {
            "USUBJID": ["P001", "P002", "P003"],
            "AGE": [45, 72, 38],
            "AGE_GROUP": ["adult", "senior", "adult"],
        }
    )
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    adam_csv = output_dir / f"{workflow_id}_adam.csv"
    adam_df.to_csv(adam_csv, index=False)

    # Patch settings to point to the temp output dir and register the workflow as known
    with patch("src.api.routers.data.get_settings") as mock_settings:
        mock_settings.return_value.output_dir = str(output_dir)
        # Register the workflow by starting one (then override is_known via history trick)
        from src.api.app import create_app

        app = create_app()
        manager = WorkflowManager()
        # Inject a fake historic entry so is_known() returns True
        from src.api.workflow_manager import _HistoricState  # type: ignore[attr-defined]

        manager._history[workflow_id] = _HistoricState(  # type: ignore[attr-defined]
            workflow_id, "completed", '{"derived_variables": [], "errors": []}'
        )
        app.state.workflow_manager = manager

        transport = ASGITransport(app=app)  # type: ignore[arg-type]
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # Act
            response = await ac.get(f"/api/v1/workflows/{workflow_id}/data")

    # Assert
    assert response.status_code == 200
    body: dict[str, object] = response.json()
    assert body["workflow_id"] == workflow_id
    assert body["derived"] is not None
    derived: dict[str, object] = body["derived"]  # type: ignore[assignment]
    assert derived["row_count"] == 3
    assert derived["column_count"] == 3
    assert len(derived["columns"]) == 3  # type: ignore[arg-type]
    derived_formats: list[str] = body["derived_formats"]  # type: ignore[assignment]
    assert "csv" in derived_formats


async def test_download_adam_default_csv_format(client: AsyncClient, tmp_path: Path) -> None:
    """GET /adam without format param returns CSV (backward compatible)."""
    # Arrange — write a temp CSV to the output dir
    workflow_id = "test-csv-download"
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    csv_path = output_dir / f"{workflow_id}_adam.csv"
    csv_path.write_text("USUBJID,AGE\nP001,45\n")

    with patch("src.api.routers.data.get_settings") as mock_settings:
        mock_settings.return_value.output_dir = str(output_dir)

        # Act
        response = await client.get(f"/api/v1/workflows/{workflow_id}/adam")

    # Assert
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]


async def test_download_adam_parquet_format_returns_file(
    client: AsyncClient,
    tmp_path: Path,
) -> None:
    """GET /adam?format=parquet returns parquet file when it exists."""
    # Arrange — write a temp parquet file to the output dir
    workflow_id = "test-parquet-download"
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    parquet_path = output_dir / f"{workflow_id}_adam.parquet"
    pd.DataFrame({"USUBJID": ["P001"], "AGE": [45]}).to_parquet(parquet_path, index=False, engine="pyarrow")

    with patch("src.api.routers.data.get_settings") as mock_settings:
        mock_settings.return_value.output_dir = str(output_dir)

        # Act
        response = await client.get(f"/api/v1/workflows/{workflow_id}/adam?format=parquet")

    # Assert
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"


async def test_download_adam_missing_parquet_returns_404(
    client: AsyncClient,
    tmp_path: Path,
) -> None:
    """GET /adam?format=parquet returns 404 when parquet file does not exist."""
    # Arrange — output dir exists but parquet file does not
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    with patch("src.api.routers.data.get_settings") as mock_settings:
        mock_settings.return_value.output_dir = str(output_dir)

        # Act
        response = await client.get("/api/v1/workflows/no-such-wf/adam?format=parquet")

    # Assert
    assert response.status_code == 404
    detail: str = response.json()["detail"]
    assert "not found" in detail.lower()


async def test_get_pipeline_returns_definition(client: AsyncClient) -> None:
    """GET /pipeline returns the default pipeline definition."""
    # Act
    response = await client.get("/api/v1/pipeline")

    # Assert
    assert response.status_code == 200
    body: dict[str, object] = response.json()
    assert body["name"] == "clinical_derivation"
    steps: list[dict[str, object]] = body["steps"]  # type: ignore[assignment]
    assert len(steps) >= 5
    step_ids = [s["id"] for s in steps]
    assert "parse_spec" in step_ids
    assert "human_review" in step_ids
