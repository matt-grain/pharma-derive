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
from src.persistence.database import init_db
from src.persistence.workflow_state_repo import WorkflowStateRepository

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


_mcp_app = mcp_server.http_app()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Initialize WorkflowManager and MCP server on startup."""
    manager = WorkflowManager()
    session_factory = await init_db()
    async with session_factory() as session:
        state_repo = WorkflowStateRepository(session)
        await manager.load_history(state_repo)
    app.state.workflow_manager = manager
    set_app_ref(app)
    # Chain the MCP server lifespan so its StreamableHTTP task group initializes
    async with _mcp_app.lifespan(_mcp_app):
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
    app.mount("/mcp", _mcp_app)
    return app


app = create_app()
