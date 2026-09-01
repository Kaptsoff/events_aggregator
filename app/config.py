from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(
        default=(
            "postgresql+psycopg://postgres:postgres@localhost:5432/"
            "events_aggregator"
        ),
        validation_alias=AliasChoices("DATABASE_URL", "POSTGRES_CONNECTION_STRING"),
    )
    events_provider_url: str = "https://events-provider.dev-2.python-labs.ru"
    events_provider_api_key: str = ""
    sync_interval_seconds: int = 86400
    request_timeout_seconds: float = 15.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
