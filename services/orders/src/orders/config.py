from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ORDERS_", extra="ignore")

    database_url: str = "postgresql+psycopg://orders_svc@localhost:5432/mayushi"
    seed: int = 20261102


@lru_cache
def get_settings() -> Settings:
    return Settings()
