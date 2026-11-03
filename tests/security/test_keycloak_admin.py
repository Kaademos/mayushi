"""C-CFG-01: Keycloak admin credentials are generated, never defaulted (live)."""

import os

import httpx
import pytest

from conftest import require_env

pytestmark = pytest.mark.integration

KEYCLOAK_URL = os.environ.get("KEYCLOAK_PUBLIC_URL", "http://localhost:8080")
TOKEN_URL = f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token"


def admin_token(username: str, password: str) -> httpx.Response:
    return httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": username,
            "password": password,
        },
        timeout=10,
    )


@pytest.mark.parametrize(
    ("username", "password"),
    [("admin", "admin"), ("admin", "password"), ("keycloak", "keycloak"), ("admin", "")],
)
def test_default_admin_credentials_are_rejected(username: str, password: str) -> None:
    assert admin_token(username, password).status_code == 401


def test_generated_admin_can_authenticate_and_master_requires_tls_externally() -> None:
    env = require_env("KEYCLOAK_ADMIN_USER", "KEYCLOAK_ADMIN_PASSWORD")
    response = admin_token(env["KEYCLOAK_ADMIN_USER"], env["KEYCLOAK_ADMIN_PASSWORD"])
    assert response.status_code == 200
    token = response.json()["access_token"]
    for realm in ("master", "northwind"):
        realm_repr = httpx.get(
            f"{KEYCLOAK_URL}/admin/realms/{realm}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        ).json()
        assert realm_repr["sslRequired"] in ("external", "all"), realm


def test_bootstrap_admin_is_removed_after_seed() -> None:
    env = require_env("KEYCLOAK_BOOTSTRAP_ADMIN_USER", "KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD")
    response = admin_token(
        env["KEYCLOAK_BOOTSTRAP_ADMIN_USER"], env["KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD"]
    )
    assert response.status_code == 401
