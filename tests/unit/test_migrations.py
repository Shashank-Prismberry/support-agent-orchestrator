from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from pydantic import ValidationError
from sqlalchemy import Column, Integer, MetaData, Table

from support_agent_orchestrator.config.settings import MigrationSettings
from support_agent_orchestrator.infrastructure.database import AGENT_METADATA
from support_agent_orchestrator.infrastructure.migrations import (
    ALEMBIC_VERSION_TABLE_SCHEMA,
    include_name,
    include_object,
    migration_context_options,
    validate_migration_connection,
    validate_migration_target,
)


def test_agent_alembic_configuration_uses_separate_migration_directory() -> None:
    root = Path(__file__).parents[2]
    config = Config(str(root / "alembic.ini"))
    script_directory = ScriptDirectory.from_config(config)

    assert config.get_main_option("script_location") == str(root / "migrations")
    assert config.get_main_option("sqlalchemy.url") == ""
    assert script_directory.get_heads() == ["20261126_01"]


def test_migration_context_is_explicitly_scoped_to_orchestrator() -> None:
    options = migration_context_options(connection=object(), target_metadata=AGENT_METADATA)

    assert options["target_metadata"] is AGENT_METADATA
    assert options["include_schemas"] is True
    assert options["version_table_schema"] == "orchestrator"


def test_migration_discovery_rejects_public_schema() -> None:
    assert include_name("orchestrator", "schema", {}) is True
    assert include_name("public", "schema", {}) is False
    assert include_name("public_table", "table", {"schema_name": "public"}) is False
    assert include_name("agent_table", "table", {"schema_name": "orchestrator"}) is True


def test_migration_object_filter_rejects_public_tables_and_columns() -> None:
    public_table = Table("backend_data", MetaData(schema="public"), Column("id", Integer))
    agent_table = Table("agent_data", MetaData(schema="orchestrator"), Column("id", Integer))

    assert include_object(public_table, "backend_data", "table", True, None) is False
    assert include_object(agent_table, "agent_data", "table", True, None) is True
    assert (
        include_object(
            public_table.c.id,
            "id",
            "column",
            True,
            None,
        )
        is False
    )


def test_migration_target_must_be_agent_database_and_schema() -> None:
    validate_migration_target("orchestrator_db", ("public", "orchestrator"))

    with pytest.raises(RuntimeError, match="only target orchestrator_db"):
        validate_migration_target("other_database", ("public", "orchestrator"))
    with pytest.raises(RuntimeError, match="only target orchestrator_db"):
        validate_migration_target("support_ai_db", ("public", "orchestrator"))
    with pytest.raises(RuntimeError, match="must exist in orchestrator_db"):
        validate_migration_target("orchestrator_db", ("public",))


@pytest.mark.asyncio
async def test_live_target_validation_closes_preflight_transaction() -> None:
    connection = AsyncMock()
    connection.scalar.return_value = "orchestrator_db"
    connection.scalars.return_value = ["public", "orchestrator"]

    await validate_migration_connection(connection)

    connection.rollback.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_failed_live_target_validation_also_closes_preflight_transaction() -> None:
    connection = AsyncMock()
    connection.scalar.return_value = "support_ai_db"
    connection.scalars.return_value = ["public", "orchestrator"]

    with pytest.raises(RuntimeError, match="only target orchestrator_db"):
        await validate_migration_connection(connection)

    connection.rollback.assert_awaited_once_with()


def test_alembic_requires_a_separate_migration_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AGENT_MIGRATION_DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        MigrationSettings(_env_file=None)

    monkeypatch.setenv(
        "AGENT_MIGRATION_DATABASE_URL",
        "postgresql+asyncpg://agent_migrator:example@localhost:5432/orchestrator_db",
    )
    assert MigrationSettings().database_url.get_secret_value().endswith("/orchestrator_db")


def test_migration_settings_load_dotenv_and_exported_environment_wins(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dotenv_url = "postgresql+asyncpg://dotenv:example@localhost:5433/orchestrator_db"
    exported_url = "postgresql+asyncpg://shell:example@localhost:5434/orchestrator_db"
    env_file = tmp_path / ".env"
    env_file.write_text(f"AGENT_MIGRATION_DATABASE_URL={dotenv_url}\n")
    monkeypatch.delenv("AGENT_MIGRATION_DATABASE_URL", raising=False)

    assert MigrationSettings(_env_file=env_file).database_url.get_secret_value() == dotenv_url

    monkeypatch.setenv("AGENT_MIGRATION_DATABASE_URL", exported_url)
    assert MigrationSettings(_env_file=env_file).database_url.get_secret_value() == exported_url


def test_migration_settings_reject_backend_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "AGENT_MIGRATION_DATABASE_URL",
        "postgresql+asyncpg://agent_migrator:example@localhost:5432/support_ai_db",
    )

    with pytest.raises(ValidationError, match="must target orchestrator_db"):
        MigrationSettings()


def test_alembic_version_table_schema_is_agent_owned() -> None:
    assert ALEMBIC_VERSION_TABLE_SCHEMA == "orchestrator"
