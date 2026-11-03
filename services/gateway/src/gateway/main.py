import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gateway.auth import CachedJwks, TokenVerifier, http_jwks_fetcher
from gateway.config import Settings, get_settings
from gateway.errors import register_error_handlers
from gateway.routers import health, me


def _default_verifier(settings: Settings) -> TokenVerifier:
    key_set = CachedJwks(
        http_jwks_fetcher(settings.oidc_jwks_url),
        ttl_seconds=settings.jwks_cache_ttl_seconds,
        min_refresh_interval_seconds=settings.jwks_min_refresh_interval_seconds,
    )
    return TokenVerifier(
        issuer=settings.oidc_issuer,
        audience=settings.oidc_audience,
        key_set=key_set,
        algorithms=settings.oidc_algorithms,
        leeway_seconds=settings.oidc_leeway_seconds,
    )


def create_app(
    settings: Settings | None = None,
    token_verifier: TokenVerifier | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO)

    docs_enabled = not settings.is_production
    app = FastAPI(
        title="Mayushi Gateway",
        version="0.1.0",
        docs_url="/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    app.state.settings = settings
    app.state.token_verifier = token_verifier or _default_verifier(settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        max_age=600,
    )

    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(me.router)
    return app


app = create_app()
