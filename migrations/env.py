"""Agent-owned Alembic environment; orchestrator_db.orchestrator must exist first."""

import asyncio

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from support_agent_orchestrator.config.settings import MigrationSettings
from support_agent_orchestrator.infrastructure import acceptance_tables
from support_agent_orchestrator.infrastructure.database import AGENT_SCHEMA
from support_agent_orchestrator.infrastructure.migrations import (
    migration_context_options,
    validate_migration_connection,
)

config = context.config
target_metadata = acceptance_tables.metadata


def run_migrations_offline() -> None:
    """Disallow offline SQL generation, which cannot verify its target database."""

    raise RuntimeError("Offline migrations are disabled; a checked database connection is required")


def run_sync_migrations(connection: Connection) -> None:
    """Configure the migration context after online target validation."""

    context.configure(**migration_context_options(connection, target_metadata))
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    settings = MigrationSettings()
    engine = create_async_engine(
        settings.database_url.get_secret_value(),
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": AGENT_SCHEMA}},
    )
    try:
        async with engine.connect() as connection:
            await validate_migration_connection(connection)
            await connection.run_sync(run_sync_migrations)
    finally:
        await engine.dispose()


def run_migrations_online() -> None:
    """Run migrations only after checking database and schema identity."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
