"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.dependencies import set_app_ref
from src.api.mcp_server import mcp as mcp_server
from src.api.routers.health import router as health_router
from src.api.routers.specs import router as specs_router
from src.api.routers.workflows import router as workflows_router
from src.api.workflow_manager import WorkflowManager
from src.config.settings import get_settings

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Initialize WorkflowManager on startup."""
    app.state.workflow_manager = WorkflowManager()
    set_app_ref(app)
    yield


def create_app() -> FastAPI:
    """Build the FastAPI application."""
    settings = get_settings()
    app = FastAPI(
        title="CDDE API",
        description="Clinical Data Derivation Engine — REST API",
        version="0.1.0",
        lifespan=lifespan,
    )
    origins = [o.strip() for o in settings.cors_origins.split(",")]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(workflows_router)
    app.include_router(specs_router)
    app.mount("/mcp", mcp_server.http_app())
    return app


app = create_app()
