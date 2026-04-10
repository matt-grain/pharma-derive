"""Tests for the FastMCP server."""

from __future__ import annotations


async def test_mcp_server_has_three_tools() -> None:
    """MCP server exposes exactly 3 tools for workflow operations."""
    # Arrange
    from src.api.mcp_server import mcp

    # Act
    tools = await mcp.list_tools()

    # Assert
    assert len(tools) == 3
    names = {t.name for t in tools}
    assert names == {"run_workflow", "get_workflow_status", "get_workflow_result"}


async def test_mcp_run_workflow_tool_has_description() -> None:
    """run_workflow tool has a description for LLM consumption."""
    # Arrange
    from src.api.mcp_server import mcp

    # Act
    tools = await mcp.list_tools()
    run_tool = next(t for t in tools if t.name == "run_workflow")

    # Assert
    assert run_tool.description
    assert "workflow" in run_tool.description.lower()
