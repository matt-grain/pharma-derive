"""Factory for creating a fully-wired DerivationOrchestrator with persistence."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from src.engine.orchestrator import DerivationOrchestrator
from src.persistence.database import init_db
from src.persistence.repositories import (
    PatternRepository,
    QCHistoryRepository,
    WorkflowStateRepository,
)

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession


async def create_orchestrator(
    spec_path: str | Path,
    llm_base_url: str = "http://localhost:8650/v1",
    output_dir: Path | None = None,
    database_url: str | None = None,
) -> tuple[DerivationOrchestrator, AsyncSession]:
    """Create an orchestrator with SQLite persistence wired up.

    Returns (orchestrator, session). Caller must commit and close the session.
    Uses DATABASE_URL env var or defaults to sqlite+aiosqlite:///cdde.db.
    """
    url = database_url or os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///cdde.db")
    session_factory = await init_db(url)
    session = session_factory()

    orch = DerivationOrchestrator(
        spec_path=spec_path,
        llm_base_url=llm_base_url,
        pattern_repo=PatternRepository(session),
        qc_repo=QCHistoryRepository(session),
        state_repo=WorkflowStateRepository(session),
        output_dir=output_dir,
    )
    return orch, session
