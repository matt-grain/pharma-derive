"""FastAPI dependency injection factories."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI, Request

from src.api.workflow_manager import WorkflowManager

_app_ref: FastAPI | None = None


def set_app_ref(app: FastAPI) -> None:
    """Store app reference for MCP tools that run outside request context."""
    global _app_ref
    _app_ref = app


def get_workflow_manager_from_app() -> WorkflowManager:
    """Get the WorkflowManager from the running app. Used by MCP tools."""
    if _app_ref is None:
        msg = "App not initialized — call set_app_ref() during lifespan startup"
        raise RuntimeError(msg)
    return _app_ref.state.workflow_manager  # type: ignore[no-any-return]  # FastAPI state is untyped


def get_workflow_manager(request: Request) -> WorkflowManager:
    """Get the singleton WorkflowManager from app state."""
    return request.app.state.workflow_manager  # type: ignore[no-any-return]  # FastAPI state is untyped


WorkflowManagerDep = Annotated[WorkflowManager, Depends(get_workflow_manager)]
