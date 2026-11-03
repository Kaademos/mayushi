from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from gateway.config import Settings
from gateway.db import get_session
from tests.conftest import AUDIENCE, ISSUER, StaticKeySet, build_app


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "ENV": "production",
        "oidc_issuer": ISSUER,
        "oidc_audience": AUDIENCE,
        "oidc_jwks_url": "http://keycloak.test/certs",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_healthz(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}


def test_readyz_reports_database_failure(settings: Settings, key_set: StaticKeySet) -> None:
    async def broken_session() -> AsyncIterator[AsyncMock]:
        session = AsyncMock()
        session.execute.side_effect = OperationalError("SELECT 1", {}, Exception("down"))
        yield session

    app = build_app(settings, key_set)
    app.dependency_overrides[get_session] = broken_session
    with TestClient(app) as client:
        response = client.get("/readyz")
    assert response.status_code == 503
    assert "down" not in response.text


def test_settings_default_to_production() -> None:
    assert Settings().is_production


def test_unknown_environment_is_refused() -> None:
    with pytest.raises(ValidationError):
        _settings(ENV="prod")


def test_docs_served_in_development(client: TestClient) -> None:
    assert client.get("/openapi.json").status_code == 200


def test_docs_hidden_in_production(key_set: StaticKeySet) -> None:
    with TestClient(build_app(_settings(), key_set)) as client:
        assert client.get("/openapi.json").status_code == 404
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404


def test_cors_preflight_allows_web_origin(client: TestClient) -> None:
    response = client.options(
        "/api/me",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.headers["access-control-allow-credentials"] == "true"


@pytest.mark.parametrize(
    "origin",
    ["https://evil.example", "http://localhost:3001", "http://localhost:3000.evil.example", "null"],
)
def test_cors_does_not_reflect_other_origins(client: TestClient, origin: str) -> None:
    preflight = client.options(
        "/api/me",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in preflight.headers
    simple = client.get("/healthz", headers={"Origin": origin})
    # Starlette always sends Allow-Credentials when enabled; without a matching
    # Allow-Origin the browser still refuses to expose the response.
    assert "access-control-allow-origin" not in simple.headers


@pytest.mark.parametrize(
    "origins",
    [["*"], ["https://*.example.com"], ["http://localhost:3000/app"], ["localhost:3000"]],
)
def test_wildcard_or_malformed_cors_origins_are_refused(origins: list[str]) -> None:
    with pytest.raises(ValidationError):
        _settings(cors_origins=origins)


def test_symmetric_jwt_algorithms_cannot_be_configured() -> None:
    with pytest.raises(ValidationError):
        _settings(oidc_algorithms=("RS256", "HS256"))


def _failing_client(settings: Settings, key_set: StaticKeySet) -> TestClient:
    app = build_app(settings, key_set)

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("kaboom: secret internal detail")

    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("env", ["development", "test", "production"])
def test_unhandled_errors_never_expose_internals(key_set: StaticKeySet, env: str) -> None:
    response = _failing_client(_settings(ENV=env), key_set).get(
        "/boom", headers={"X-Request-ID": "req-12345678"}
    )
    assert response.status_code == 500
    assert response.json() == {
        "error": "internal_error",
        "message": "An unexpected error occurred.",
        "correlation_id": "req-12345678",
    }
    assert response.headers["x-request-id"] == "req-12345678"
    assert "kaboom" not in response.text
    assert "Traceback" not in response.text


def test_malformed_request_id_is_replaced(key_set: StaticKeySet) -> None:
    response = _failing_client(_settings(), key_set).get(
        "/boom", headers={"X-Request-ID": "<script>alert(1)</script>"}
    )
    correlation_id = response.json()["correlation_id"]
    assert correlation_id != "<script>alert(1)</script>"
    assert len(correlation_id) == 32
