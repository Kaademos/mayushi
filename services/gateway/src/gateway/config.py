from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GATEWAY_", extra="ignore")

    env: Environment = Field(default="production", validation_alias="ENV")

    database_url: str = "postgresql+psycopg://gateway_svc@localhost:5432/mayushi"

    oidc_issuer: str = "http://localhost:8080/realms/northwind"
    oidc_jwks_url: str = "http://localhost:8080/realms/northwind/protocol/openid-connect/certs"
    oidc_audience: str = "mayushi-api"
    oidc_algorithms: tuple[str, ...] = ("RS256", "ES256")
    oidc_leeway_seconds: int = Field(default=30, ge=0, le=120)
    jwks_cache_ttl_seconds: int = Field(default=300, ge=30)
    jwks_min_refresh_interval_seconds: int = Field(default=30, ge=1)

    cors_origins: list[str] = ["http://localhost:3000"]

    @field_validator("oidc_algorithms")
    @classmethod
    def _asymmetric_algorithms_only(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        allowed = {"RS256", "ES256"}
        if not value or not set(value) <= allowed:
            raise ValueError(f"oidc_algorithms must be a non-empty subset of {sorted(allowed)}")
        return value

    @field_validator("cors_origins")
    @classmethod
    def _explicit_origins_only(cls, value: list[str]) -> list[str]:
        for origin in value:
            parts = urlsplit(origin)
            if (
                parts.scheme not in ("http", "https")
                or not parts.hostname
                or "*" in origin
                or parts.path not in ("", "/")
                or parts.query
                or parts.fragment
            ):
                raise ValueError(f"invalid CORS origin: {origin!r}")
        return [origin.rstrip("/") for origin in value]

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
