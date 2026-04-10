# Phase 11.2 — FastMCP Thin Layer

**Depends on:** Phase 11.1 (FastAPI REST API must exist — MCP tools wrap the same WorkflowManager)
**Agent:** `python-mcp-expert`
**Goal:** Expose the orchestrator as MCP tools so LLM agents can drive workflows programmatically. FastMCP 3.0 mounted on the existing FastAPI app via SSE transport.

---

## 1. Add dependency — `pyproject.toml` (MODIFY)

**Change:** Add FastMCP:
```toml
"fastmcp>=3.0,<4",
```

---

## 2. MCP Server — `src/api/mcp_server.py` (NEW)

**Purpose:** Thin FastMCP server exposing 3 MCP tools that delegate to the WorkflowManager. Mounted on the FastAPI app at `/mcp/`.

```python
"""FastMCP server — exposes orchestrator operations as MCP tools for LLM agents."""

from __future__ import annotations

from fastmcp import FastMCP

mcp = FastMCP(
    name="cdde",
    instructions="Clinical Data Derivation Engine. Use these tools to run derivation workflows, check status, and retrieve results.",
)

@mcp.tool()
async def run_workflow(spec_path: str, llm_base_url: str | None = None) -> dict[str, str]:
    """Start a new derivation workflow.
    
    Args:
        spec_path: Relative path to the YAML transformation spec (e.g. "specs/cdiscpilot01_adsl.yaml")
        llm_base_url: Optional LLM endpoint override
    
    Returns:
        dict with workflow_id and status
    """
    from src.api.dependencies import get_workflow_manager_from_app
    manager = get_workflow_manager_from_app()
    wf_id = await manager.start_workflow(spec_path, llm_base_url)
    return {"workflow_id": wf_id, "status": "started"}

@mcp.tool()
async def get_workflow_status(workflow_id: str) -> dict[str, object]:
    """Get current status of a running or completed workflow.
    
    Args:
        workflow_id: The workflow ID returned by run_workflow
    
    Returns:
        dict with status, derived_variables, errors
    """
    from src.api.dependencies import get_workflow_manager_from_app
    manager = get_workflow_manager_from_app()
    orch = manager.get_orchestrator(workflow_id)
    if orch is None:
        return {"error": f"Workflow {workflow_id} not found"}
    fsm_state = str(orch.fsm.current_state_value or "unknown")
    return {
        "workflow_id": workflow_id,
        "status": fsm_state,
        "is_running": manager.is_running(workflow_id),
        "derived_variables": list(orch.state.dag.nodes.keys()) if orch.state.dag else [],
        "errors": orch.state.errors,
    }

@mcp.tool()
async def get_workflow_result(workflow_id: str) -> dict[str, object]:
    """Get the full result of a completed workflow including QC summary and audit.
    
    Args:
        workflow_id: The workflow ID returned by run_workflow
    
    Returns:
        dict with full result or error if not completed
    """
    from src.api.dependencies import get_workflow_manager_from_app
    manager = get_workflow_manager_from_app()
    result = manager.get_result(workflow_id)
    if result is None:
        if manager.is_running(workflow_id):
            return {"error": "Workflow still running", "workflow_id": workflow_id}
        return {"error": f"Workflow {workflow_id} not found"}
    return result.model_dump()
```

**Constraints:**
- FastMCP 3.0 API — `@mcp.tool()` decorator
- Tools return plain `dict` (MCP protocol requires JSON-serializable returns)
- Lazy import `get_workflow_manager_from_app` inside tools to avoid circular imports (the MCP server is created at module level but the app isn't available yet)
- Tool docstrings are the MCP tool descriptions — make them clear for LLM consumption

---

## 3. Mount MCP on FastAPI — `src/api/app.py` (MODIFY)

**Change:** Mount the FastMCP server as an SSE endpoint on the FastAPI app:

```python
from src.api.mcp_server import mcp

# In create_app(), after router registration:
# NOTE: FastMCP.mount() is for MCP-to-MCP. For FastAPI integration, use http_app():
app.mount("/mcp", mcp.http_app())
```

**Also add** a `get_workflow_manager_from_app` helper in `src/api/dependencies.py`:
```python
# Module-level reference set during lifespan
_app_ref: FastAPI | None = None

def set_app_ref(app: FastAPI) -> None:
    global _app_ref
    _app_ref = app

def get_workflow_manager_from_app() -> WorkflowManager:
    """Get the WorkflowManager from the running app. Used by MCP tools."""
    if _app_ref is None:
        raise RuntimeError("App not initialized")
    return _app_ref.state.workflow_manager
```

Call `set_app_ref(app)` in the lifespan startup.

---

## 4. Tests — `tests/unit/test_mcp.py` (NEW)

**Tests to write:**
- `test_mcp_server_has_three_tools` — verify tool count
- `test_mcp_run_workflow_tool_exists` — verify run_workflow is registered
- `test_mcp_get_status_tool_exists` — verify get_workflow_status is registered

**Pattern:** Test the MCP server object directly, not via HTTP. IMPORTANT: `list_tools()` is async in FastMCP 3.0.

```python
async def test_mcp_server_has_three_tools() -> None:
    from src.api.mcp_server import mcp
    tools = await mcp.list_tools()
    assert len(tools) == 3
    names = {t.name for t in tools}
    assert names == {"run_workflow", "get_workflow_status", "get_workflow_result"}
```

---

## Verification

1. `uv run ruff check . --fix && uv run ruff format .`
2. `uv run pyright .`
3. `uv run pytest --tb=short -q`
4. `uv run python -c "from src.api.mcp_server import mcp; print(mcp.name, len(mcp.list_tools()), 'tools')"` — smoke test
