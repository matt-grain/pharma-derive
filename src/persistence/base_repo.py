"""Base repository with shared session management and error wrapping."""

from __future__ import annotations

from typing import Any  # Any: SQLAlchemy Result[Any] — generic Row type not narrowable at this layer

from loguru import logger
from sqlalchemy import Executable  # noqa: TC002 — used in _execute param type at runtime
from sqlalchemy.engine import Result  # noqa: TC002 — used in _execute return type at runtime
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002 — stored as self._session at runtime

from src.domain.exceptions import RepositoryError


class BaseRepository:
    """Base for all repositories — provides session access and error wrapping."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _execute(self, stmt: Executable) -> Result[Any]:
        """Execute a statement with error wrapping for connection/timeout failures."""
        try:
            return await self._session.execute(stmt)
        except OperationalError as exc:
            logger.error("Query failed: {err}", err=exc)
            raise RepositoryError("execute", f"Database operational error: {exc}") from exc

    async def _flush(self) -> None:
        """Flush session with error wrapping for write operations."""
        try:
            await self._session.flush()
        except IntegrityError as exc:
            logger.error("Integrity error during flush: {err}", err=exc)
            raise RepositoryError("flush", f"Integrity constraint violated: {exc}") from exc
        except OperationalError as exc:
            logger.error("Operational error during flush: {err}", err=exc)
            raise RepositoryError("flush", f"Database operational error: {exc}") from exc

    async def commit(self) -> None:
        """Commit the underlying session — used by orchestration code to persist pending writes."""
        try:
            await self._session.commit()
        except (IntegrityError, OperationalError) as exc:
            logger.error("Commit failed: {err}", err=exc)
            raise RepositoryError("commit", f"Database commit failed: {exc}") from exc
