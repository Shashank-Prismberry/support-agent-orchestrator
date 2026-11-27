"""Safety policy shared by the Agent Alembic environment and its tests."""

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from support_agent_orchestrator.config.settings import AGENT_DATABASE
from support_agent_orchestrator.infrastructure.database import AGENT_SCHEMA

ALEMBIC_VERSION_TABLE_SCHEMA = AGENT_SCHEMA


def validate_migration_target(database: str, schemas: Sequence[str]) -> None:
    """Fail closed unless the Agent database and schema are already provisioned."""

    if database != AGENT_DATABASE:
        raise RuntimeError(f"Agent migrations may only target {AGENT_DATABASE}")
    if AGENT_SCHEMA not in schemas:
        raise RuntimeError(
            f"The {AGENT_SCHEMA} schema must exist in {AGENT_DATABASE} before migration"
        )


async def validate_migration_connection(connection: AsyncConnection) -> None:
    """Validate the live target and close the read-only preflight transaction."""

    try:
        database = await connection.scalar(text("SELECT current_database()"))
        schemas = await connection.scalars(
            text("SELECT schema_name FROM information_schema.schemata")
        )
        validate_migration_target(database, tuple(schemas))
    finally:
        # The SELECTs autobegin a transaction. Clear it before Alembic takes
        # ownership of the connection, or its DDL may be rolled back on close.
        await connection.rollback()


def include_name(name: str | None, type_: str, parent_names: Mapping[str, Any]) -> bool:
    """Restrict Alembic autogeneration discovery to the Agent schema."""

    if type_ == "schema":
        return name == AGENT_SCHEMA
    if type_ in {"table", "table_name"}:
        return parent_names.get("schema_name") == AGENT_SCHEMA
    return True


def include_object(
    obj: Any,
    name: str,
    type_: str,
    reflected: bool,
    compare_to: Any,
) -> bool:
    """Reject autogeneration objects associated with any non-Agent schema."""

    del name, reflected, compare_to
    if type_ == "table":
        return getattr(obj, "schema", None) == AGENT_SCHEMA
    table = getattr(obj, "table", None)
    if table is not None:
        return getattr(table, "schema", None) == AGENT_SCHEMA
    return True


def migration_context_options(connection: Any, target_metadata: Any) -> dict[str, Any]:
    """Build Alembic options that bind versioning and discovery to orchestrator."""

    return {
        "connection": connection,
        "target_metadata": target_metadata,
        "include_schemas": True,
        "include_name": include_name,
        "include_object": include_object,
        "version_table_schema": ALEMBIC_VERSION_TABLE_SCHEMA,
    }
