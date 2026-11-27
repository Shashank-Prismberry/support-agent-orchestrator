"""Asynchronous SQLAlchemy engine and session lifecycle."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from support_agent_orchestrator.config.settings import Settings

AGENT_SCHEMA = "orchestrator"
AGENT_METADATA = MetaData(schema=AGENT_SCHEMA)


def create_database_engine(settings: Settings) -> AsyncEngine:
    """Create an async engine scoped to the Agent-owned database schema."""

    return create_async_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        connect_args={"server_settings": {"search_path": AGENT_SCHEMA}},
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create a factory for short-lived, operation-scoped async sessions."""

    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def session_scope(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Yield one session and always close it; callers own transaction boundaries."""

    async with factory() as session:
        yield session


async def dispose_database_engine(engine: AsyncEngine) -> None:
    """Dispose the process-owned pool during application or worker shutdown."""

    await engine.dispose()
