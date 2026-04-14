"""PostgreSQL async engine + session factory."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(url: str) -> AsyncEngine:
    """Create an async SQLAlchemy engine from a DATABASE_URL string."""
    return create_async_engine(url, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Return a session factory that produces AsyncSession instances."""
    return async_sessionmaker(engine, expire_on_commit=False)
