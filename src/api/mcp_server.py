"""FastMCP server — exposes orchestrator operations as MCP tools for LLM agents."""

from __future__ import annotations

from typing import Any  # Any: MCP protocol returns mixed JSON types

from fastmcp import FastMCP

mcp = FastMCP(
    name="cdde",
    instructions=(
        "Clinical Data Derivation Engine. Use these tools to run derivation "
        "workflows, check status, and retrieve results."
    ),
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
async def get_workflow_status(workflow_id: str) -> dict[str, Any]:
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
async def get_workflow_result(workflow_id: str) -> dict[str, Any]:
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
