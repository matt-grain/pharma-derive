"""Database initialization — engine, session factory, table creation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config.settings import get_settings
from src.persistence.orm_models import Base

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


async def init_db(
    database_url: str | None = None,
) -> async_sessionmaker[AsyncSession]:
    """Create engine + session factory. Creates tables if needed."""
    url = database_url or get_settings().database_url
    is_sqlite = url.startswith("sqlite")
    engine = create_async_engine(
        url,
        echo=False,
        pool_pre_ping=True,
        **({} if is_sqlite else {"pool_size": 5, "max_overflow": 10, "pool_timeout": 30}),
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession]:
    """Yield an async session."""
    async with session_factory() as session:
        yield session
