from __future__ import annotations

import os
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.persistence.orm_models import Base

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


async def init_db(
    database_url: str | None = None,
) -> async_sessionmaker[AsyncSession]:
    """Create engine + session factory. Creates tables if needed."""
    url = database_url or os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///cdde.db")
    engine = create_async_engine(url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession]:
    """Yield an async session."""
    async with session_factory() as session:
        yield session
