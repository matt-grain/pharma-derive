"""Tests for shared agent tools: inspect_data and execute_code.

All tests are offline — tools are called directly without LLM involvement.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic_ai import RunContext

    from src.agents.deps import CoderDeps

from src.agents.tools import execute_code, inspect_data

# ---------------------------------------------------------------------------
# inspect_data tests
# ---------------------------------------------------------------------------


async def test_inspect_data_returns_schema_section(mock_ctx: RunContext[CoderDeps]) -> None:
    # Act
    result = await inspect_data(mock_ctx)

    # Assert
    assert "SCHEMA" in result
    assert "age" in result
    assert "patient_id" in result


async def test_inspect_data_returns_nulls_section(mock_ctx: RunContext[CoderDeps]) -> None:
    # Act
    result = await inspect_data(mock_ctx)

    # Assert
    assert "NULLS" in result
    assert "1 null" in result  # age column has 1 null in the fixture


async def test_inspect_data_returns_aggregates_only(mock_ctx: RunContext[CoderDeps]) -> None:
    """inspect_data must not leak raw patient identifiers in the analysis sections."""
    # Act
    result = await inspect_data(mock_ctx)

    # Assert — patient IDs must not appear in schema/nulls/ranges, only in synthetic CSV
    analysis_sections = result.split("=== SYNTHETIC SAMPLE ===")[0]
    assert "P001" not in analysis_sections
    assert "P002" not in analysis_sections


async def test_inspect_data_includes_synthetic_sample(mock_ctx: RunContext[CoderDeps]) -> None:
    # Act
    result = await inspect_data(mock_ctx)

    # Assert
    assert "SYNTHETIC SAMPLE" in result


# ---------------------------------------------------------------------------
# execute_code — happy path
# ---------------------------------------------------------------------------


async def test_execute_code_returns_result_summary(mock_ctx: RunContext[CoderDeps]) -> None:
    # Act
    output = await execute_code(mock_ctx, "result = df['age'] * 2")

    # Assert
    assert "dtype" in output
    assert "null_count" in output


async def test_execute_code_returns_summary_not_raw_rows(mock_ctx: RunContext[CoderDeps]) -> None:
    """execute_code returns aggregate Series stats, not individual patient rows."""
    # Act
    output = await execute_code(mock_ctx, "result = df['age']")

    # Assert
    assert "dtype" in output
    assert "null_count" in output
    assert "P001" not in output  # no raw patient identifiers


async def test_execute_code_handles_no_result_variable(mock_ctx: RunContext[CoderDeps]) -> None:
    # Act
    output = await execute_code(mock_ctx, "x = 42")

    # Assert
    assert "result" in output.lower() or "no output" in output.lower()


async def test_execute_code_captures_runtime_errors(mock_ctx: RunContext[CoderDeps]) -> None:
    # Act
    output = await execute_code(mock_ctx, "result = df['nonexistent_column']")

    # Assert
    assert "ERROR" in output
    assert "KeyError" in output


# ---------------------------------------------------------------------------
# execute_code — security / sandbox tests
# ---------------------------------------------------------------------------


async def test_execute_code_blocks_dangerous_imports(mock_ctx: RunContext[CoderDeps]) -> None:
    # Act
    output = await execute_code(mock_ctx, "import os; os.system('echo pwned')")

    # Assert
    assert "BLOCKED" in output
    assert "import" in output


async def test_execute_code_blocks_file_access(mock_ctx: RunContext[CoderDeps]) -> None:
    # Act
    output = await execute_code(mock_ctx, "open('/etc/passwd')")

    # Assert
    assert "BLOCKED" in output
    assert "open" in output


async def test_execute_code_blocks_eval(mock_ctx: RunContext[CoderDeps]) -> None:
    # Act
    output = await execute_code(mock_ctx, "eval('1+1')")

    # Assert
    assert "BLOCKED" in output


async def test_execute_code_blocks_exec(mock_ctx: RunContext[CoderDeps]) -> None:
    # Act
    output = await execute_code(mock_ctx, "exec('x=1')")

    # Assert
    assert "BLOCKED" in output


async def test_execute_code_blocks_dunder_import(mock_ctx: RunContext[CoderDeps]) -> None:
    # Act
    output = await execute_code(mock_ctx, "__import__('os')")

    # Assert
    assert "BLOCKED" in output
