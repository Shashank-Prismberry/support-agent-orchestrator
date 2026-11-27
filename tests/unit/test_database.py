import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from support_agent_orchestrator.config.settings import ROOT_ENV_FILE, Settings
from support_agent_orchestrator.infrastructure import database

VALID_DATABASE_URL = "postgresql+asyncpg://agent:example@localhost:5432/orchestrator_db"


def test_settings_accepts_agent_postgres_url_and_masks_secret() -> None:
    settings = Settings(database_url=VALID_DATABASE_URL)

    assert isinstance(settings.database_url, SecretStr)
    assert settings.database_url.get_secret_value() == VALID_DATABASE_URL
    assert "example" not in repr(settings)


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql://agent:example@localhost:5432/support_ai_db",
        "postgresql+asyncpg://agent:example@localhost:5432/public",
        "postgresql+asyncpg://agent:example@localhost:5432/support_ai_db",
        "not-a-database-url",
    ],
)
def test_settings_rejects_wrong_driver_or_database(database_url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(database_url=database_url)


def test_settings_reads_database_url_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", VALID_DATABASE_URL)

    assert Settings().database_url.get_secret_value() == VALID_DATABASE_URL


def test_settings_load_dotenv_and_exported_environment_wins(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dotenv_url = "postgresql+asyncpg://dotenv:example@localhost:5433/orchestrator_db"
    exported_url = "postgresql+asyncpg://shell:example@localhost:5434/orchestrator_db"
    env_file = tmp_path / ".env"
    env_file.write_text(f"DATABASE_URL={dotenv_url}\n")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert Settings(_env_file=env_file).database_url.get_secret_value() == dotenv_url

    monkeypatch.setenv("DATABASE_URL", exported_url)
    assert Settings(_env_file=env_file).database_url.get_secret_value() == exported_url


def test_settings_default_to_repository_root_env_file() -> None:
    root = Path(__file__).parents[2]
    assert Settings.model_config["env_file"] == root / ".env"


def test_pytest_bootstrap_loads_test_url_from_root_env_when_configured() -> None:
    from dotenv import dotenv_values

    if not dotenv_values(ROOT_ENV_FILE).get("TEST_DATABASE_URL"):
        pytest.skip("root .env does not configure PostgreSQL integration tests")

    assert os.environ.get("TEST_DATABASE_URL")


def test_runtime_settings_do_not_require_migration_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", VALID_DATABASE_URL)
    monkeypatch.delenv("AGENT_MIGRATION_DATABASE_URL", raising=False)

    assert Settings().database_url.get_secret_value() == VALID_DATABASE_URL


def test_engine_construction_does_not_connect_and_sets_agent_search_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_create_async_engine(url: str, **kwargs: object) -> object:
        captured["url"] = url
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(database, "create_async_engine", fake_create_async_engine)

    engine = database.create_database_engine(Settings(database_url=VALID_DATABASE_URL))

    assert captured["url"] == VALID_DATABASE_URL
    assert captured["pool_pre_ping"] is True
    assert captured["connect_args"] == {"server_settings": {"search_path": "orchestrator"}}
    assert engine is not None


@pytest.mark.asyncio
async def test_real_async_engine_constructs_without_a_live_database() -> None:
    engine = database.create_database_engine(Settings(database_url=VALID_DATABASE_URL))
    try:
        assert engine.url.database == "orchestrator_db"
        assert engine.sync_engine.dialect.name == "postgresql"
        assert engine.sync_engine.dialect.is_async is True
    finally:
        await database.dispose_database_engine(engine)


def test_session_factory_does_not_expire_objects_on_commit() -> None:
    engine = AsyncMock(spec=AsyncEngine)
    factory = database.create_session_factory(engine)

    assert factory.kw["bind"] is engine
    assert factory.kw["expire_on_commit"] is False


@pytest.mark.asyncio
async def test_session_scope_closes_session_after_success() -> None:
    closed = False
    session = object()

    @asynccontextmanager
    async def factory() -> AsyncIterator[object]:
        nonlocal closed
        try:
            yield session
        finally:
            closed = True

    async with database.session_scope(factory) as yielded_session:  # type: ignore[arg-type]
        assert yielded_session is session
        assert closed is False

    assert closed is True


@pytest.mark.asyncio
async def test_session_scope_closes_session_after_exception() -> None:
    closed = False

    @asynccontextmanager
    async def factory() -> AsyncIterator[AsyncSession]:
        nonlocal closed
        try:
            yield AsyncMock(spec=AsyncSession)
        finally:
            closed = True

    with pytest.raises(RuntimeError, match="operation failed"):
        async with database.session_scope(factory):  # type: ignore[arg-type]
            raise RuntimeError("operation failed")

    assert closed is True


@pytest.mark.asyncio
async def test_engine_disposal_calls_pool_dispose() -> None:
    engine = AsyncMock()

    await database.dispose_database_engine(engine)

    engine.dispose.assert_awaited_once_with()
