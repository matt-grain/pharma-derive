"""Health check endpoint for Docker/K8s probes."""

from __future__ import annotations

from fastapi import APIRouter

from src.api.dependencies import (
    WorkflowManagerDep,  # noqa: TC001 — FastAPI resolves Annotated[Depends] at runtime via get_type_hints()
)
from src.api.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, status_code=200)
async def health_check(manager: WorkflowManagerDep) -> HealthResponse:
    """Liveness check with active workflow count."""
    return HealthResponse(status="ok", version="0.1.0", workflows_in_progress=manager.active_count)
