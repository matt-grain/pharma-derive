"""Tests for shared agent tools: inspect_data and execute_code.

All tests are offline — tools are called directly without LLM involvement.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pydantic_ai import RunContext

from src.agents.tools import CoderDeps, execute_code, inspect_data

# ---------------------------------------------------------------------------
# inspect_data tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_inspect_data_returns_schema_section(mock_ctx: RunContext[CoderDeps]) -> None:
    result = await inspect_data(mock_ctx)

    assert "SCHEMA" in result
    assert "age" in result
    assert "patient_id" in result


@pytest.mark.asyncio
async def test_inspect_data_returns_nulls_section(mock_ctx: RunContext[CoderDeps]) -> None:
    result = await inspect_data(mock_ctx)

    assert "NULLS" in result
    assert "1 null" in result  # age column has 1 null in the fixture


@pytest.mark.asyncio
async def test_inspect_data_returns_aggregates_only(mock_ctx: RunContext[CoderDeps]) -> None:
    """inspect_data must not leak raw patient identifiers in the analysis sections."""
    result = await inspect_data(mock_ctx)

    # Patient IDs must not appear in schema/nulls/ranges — only in the synthetic CSV section.
    analysis_sections = result.split("=== SYNTHETIC SAMPLE ===")[0]
    assert "P001" not in analysis_sections
    assert "P002" not in analysis_sections


@pytest.mark.asyncio
async def test_inspect_data_includes_synthetic_sample(mock_ctx: RunContext[CoderDeps]) -> None:
    result = await inspect_data(mock_ctx)

    assert "SYNTHETIC SAMPLE" in result


# ---------------------------------------------------------------------------
# execute_code — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_code_returns_result_summary(mock_ctx: RunContext[CoderDeps]) -> None:
    output = await execute_code(mock_ctx, "result = df['age'] * 2")

    assert "dtype" in output
    assert "null_count" in output


@pytest.mark.asyncio
async def test_execute_code_returns_summary_not_raw_rows(mock_ctx: RunContext[CoderDeps]) -> None:
    """execute_code returns aggregate Series stats, not individual patient rows."""
    output = await execute_code(mock_ctx, "result = df['age']")

    assert "dtype" in output
    assert "null_count" in output
    assert "P001" not in output  # no raw patient identifiers


@pytest.mark.asyncio
async def test_execute_code_handles_no_result_variable(mock_ctx: RunContext[CoderDeps]) -> None:
    output = await execute_code(mock_ctx, "x = 42")

    assert "result" in output.lower() or "no output" in output.lower()


@pytest.mark.asyncio
async def test_execute_code_captures_runtime_errors(mock_ctx: RunContext[CoderDeps]) -> None:
    output = await execute_code(mock_ctx, "result = df['nonexistent_column']")

    assert "ERROR" in output
    assert "KeyError" in output


# ---------------------------------------------------------------------------
# execute_code — security / sandbox tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_code_blocks_dangerous_imports(mock_ctx: RunContext[CoderDeps]) -> None:
    output = await execute_code(mock_ctx, "import os; os.system('echo pwned')")

    assert "BLOCKED" in output
    assert "import" in output


@pytest.mark.asyncio
async def test_execute_code_blocks_file_access(mock_ctx: RunContext[CoderDeps]) -> None:
    output = await execute_code(mock_ctx, "open('/etc/passwd')")

    assert "BLOCKED" in output
    assert "open" in output


@pytest.mark.asyncio
async def test_execute_code_blocks_eval(mock_ctx: RunContext[CoderDeps]) -> None:
    output = await execute_code(mock_ctx, "eval('1+1')")

    assert "BLOCKED" in output


@pytest.mark.asyncio
async def test_execute_code_blocks_exec(mock_ctx: RunContext[CoderDeps]) -> None:
    output = await execute_code(mock_ctx, "exec('x=1')")

    assert "BLOCKED" in output


@pytest.mark.asyncio
async def test_execute_code_blocks_dunder_import(mock_ctx: RunContext[CoderDeps]) -> None:
    output = await execute_code(mock_ctx, "__import__('os')")

    assert "BLOCKED" in output
