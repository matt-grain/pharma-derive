"""Tests for the pipeline orchestrator factory."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.factory import create_pipeline_orchestrator

# Paths that are stable across test runs
_SPEC_PATH = Path("specs/simple_mock.yaml")
_PIPELINE_PATH = Path("config/pipelines/clinical_derivation.yaml")


async def test_create_pipeline_orchestrator_returns_wired_components(
    tmp_path: Path,
) -> None:
    """Happy path: factory returns interpreter, ctx, fsm, and session."""
    # Arrange
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"

    # Act
    interpreter, ctx, fsm, session = await create_pipeline_orchestrator(
        spec_path=_SPEC_PATH,
        pipeline_path=_PIPELINE_PATH,
        output_dir=tmp_path / "output",
        database_url=db_url,
    )

    # Assert
    try:
        assert interpreter is not None
        assert ctx is not None
        assert ctx.workflow_id  # non-empty hex string
        assert fsm is not None
        assert ctx.step_outputs["_init"]["spec_path"] == _SPEC_PATH
    finally:
        await session.close()


async def test_create_pipeline_orchestrator_seeds_spec_path_in_context(
    tmp_path: Path,
) -> None:
    """Factory seeds _init.spec_path so parse_spec builtin can locate the file."""
    # Arrange
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    spec = Path("specs/simple_mock.yaml")

    # Act
    _, ctx, _, session = await create_pipeline_orchestrator(
        spec_path=spec,
        pipeline_path=_PIPELINE_PATH,
        database_url=db_url,
    )

    # Assert
    try:
        seeded_path = ctx.step_outputs["_init"]["spec_path"]
        assert seeded_path == spec
    finally:
        await session.close()


async def test_create_pipeline_orchestrator_missing_pipeline_raises(
    tmp_path: Path,
) -> None:
    """Requesting a non-existent pipeline YAML raises FileNotFoundError."""
    # Arrange
    bogus_pipeline = tmp_path / "nonexistent_pipeline.yaml"
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"

    # Act & Assert
    with pytest.raises(FileNotFoundError, match="Pipeline config not found"):
        await create_pipeline_orchestrator(
            spec_path=_SPEC_PATH,
            pipeline_path=bogus_pipeline,
            database_url=db_url,
        )


async def test_create_pipeline_orchestrator_interpreter_fsm_wired(
    tmp_path: Path,
) -> None:
    """Factory wires the FSM into the interpreter so FSM advancement works at runtime."""
    # Arrange
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"

    # Act
    interpreter, _, fsm, session = await create_pipeline_orchestrator(
        spec_path=_SPEC_PATH,
        pipeline_path=_PIPELINE_PATH,
        output_dir=tmp_path / "output",
        database_url=db_url,
    )

    # Assert
    try:
        assert interpreter._fsm is fsm  # pyright: ignore[reportPrivateUsage]
    finally:
        await session.close()
