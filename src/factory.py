"""Factory for creating a fully-wired DerivationOrchestrator with persistence."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.config.settings import get_settings
from src.engine.orchestrator import DerivationOrchestrator, OrchestratorRepos
from src.persistence import (
    PatternRepository,
    QCHistoryRepository,
    WorkflowStateRepository,
)
from src.persistence.database import init_db

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession


async def create_orchestrator(
    spec_path: str | Path,
    llm_base_url: str | None = None,
    output_dir: Path | None = None,
    database_url: str | None = None,
) -> tuple[DerivationOrchestrator, AsyncSession]:
    """Create an orchestrator with SQLite persistence wired up.

    Returns (orchestrator, session). Caller must commit and close the session.
    """
    settings = get_settings()
    url = database_url or settings.database_url
    session_factory = await init_db(url)
    session = session_factory()

    repos = OrchestratorRepos(
        pattern_repo=PatternRepository(session),
        qc_repo=QCHistoryRepository(session),
        state_repo=WorkflowStateRepository(session),
    )
    orch = DerivationOrchestrator(
        spec_path=spec_path,
        llm_base_url=llm_base_url or settings.llm_base_url,
        repos=repos,
        output_dir=output_dir,
    )
    return orch, session
