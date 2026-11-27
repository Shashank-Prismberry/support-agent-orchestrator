"""Environment-backed configuration for the Agent service."""

from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

AGENT_DATABASE = "orchestrator_db"
ROOT_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"
SETTINGS_CONFIG = SettingsConfigDict(
    env_file=ROOT_ENV_FILE,
    env_file_encoding="utf-8",
    extra="ignore",
)


class Settings(BaseSettings):
    """Runtime settings sourced from environment variables."""

    model_config = SETTINGS_CONFIG

    database_url: SecretStr

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        """Restrict application persistence to the approved async driver and database."""

        return _validate_agent_database_url(value, setting_name="DATABASE_URL")


class MigrationSettings(BaseSettings):
    """Separate credentials for Agent-owned Alembic operations."""

    model_config = SETTINGS_CONFIG

    database_url: SecretStr = Field(validation_alias="AGENT_MIGRATION_DATABASE_URL")

    @field_validator("database_url")
    @classmethod
    def validate_migration_database_url(cls, value: SecretStr) -> SecretStr:
        """Restrict migrations to the Agent database using the async driver."""

        return _validate_agent_database_url(
            value,
            setting_name="AGENT_MIGRATION_DATABASE_URL",
        )


def _validate_agent_database_url(value: SecretStr, *, setting_name: str) -> SecretStr:
    try:
        url = make_url(value.get_secret_value())
    except (ArgumentError, TypeError, ValueError):
        raise ValueError(f"{setting_name} must be a valid SQLAlchemy URL") from None

    if url.drivername != "postgresql+asyncpg":
        raise ValueError(f"{setting_name} must use the postgresql+asyncpg driver")
    if url.database != AGENT_DATABASE:
        raise ValueError(f"{setting_name} must target {AGENT_DATABASE}")
    return value
