"""Application settings — validated at startup from .env and environment variables.

Single source of truth for all configuration. Replaces scattered os.environ.get() calls.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """CDDE application settings, loaded from .env file and environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite+aiosqlite:///cdde.db"
    llm_base_url: str = "http://localhost:8650/v1"
    llm_api_key: str = "not-needed-for-mailbox"
    llm_model: str = "cdde-agent"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance. Call once at startup; cached thereafter."""
    return Settings()
