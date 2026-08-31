from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./events.db"
    events_provider_url: str = "https://events-provider.dev-2.python-labs.ru"
    events_provider_api_key: str = ""
    sync_interval_seconds: int = 86400
    request_timeout_seconds: float = 15.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
