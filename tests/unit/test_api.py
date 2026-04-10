"""Tests for the FastAPI REST API."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.workflow_manager import WorkflowManager

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


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
