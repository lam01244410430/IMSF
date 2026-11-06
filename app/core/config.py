"""Settings from environment only (no hardcoded secrets)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    database_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
