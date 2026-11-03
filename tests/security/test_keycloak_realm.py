"""C-CFG-02: realm export hardening (static checks on infra/keycloak/realm-northwind.json)."""

from typing import Any

import pytest


@pytest.fixture(scope="module")
def web_client(realm: dict[str, Any]) -> dict[str, Any]:
    clients = {c["clientId"]: c for c in realm["clients"]}
    client: dict[str, Any] = clients["mayushi-web"]
    return client


def test_tls_required_for_non_local_traffic(realm: dict[str, Any]) -> None:
    assert realm["sslRequired"] in ("external", "all")


def test_brute_force_detection(realm: dict[str, Any]) -> None:
    assert realm["bruteForceProtected"] is True
    assert realm["failureFactor"] <= 5
    assert realm["maxFailureWaitSeconds"] >= 900


def test_password_policy_is_length_based(realm: dict[str, Any]) -> None:
    rules = {r.strip().split("(")[0]: r.strip() for r in realm["passwordPolicy"].split(" and ")}
    assert rules["length"] == "length(15)"
    assert "maxLength" in rules
    assert {"notUsername", "notEmail"} <= set(rules)


def test_short_lived_access_tokens_and_refresh_rotation(realm: dict[str, Any]) -> None:
    assert realm["accessTokenLifespan"] <= 300
    assert realm["revokeRefreshToken"] is True
    assert realm["refreshTokenMaxReuse"] == 0
    assert realm["ssoSessionIdleTimeout"] <= 1800


def test_no_self_registration_or_username_edits(realm: dict[str, Any]) -> None:
    assert realm["registrationAllowed"] is False
    assert realm["editUsernameAllowed"] is False


def test_export_contains_no_credentials(realm: dict[str, Any]) -> None:
    assert all("credentials" not in user for user in realm["users"])
    assert all("secret" not in client for client in realm["clients"])


def test_web_client_is_confidential_with_pkce(web_client: dict[str, Any]) -> None:
    assert web_client["publicClient"] is False
    assert web_client["clientAuthenticatorType"] == "client-secret"
    assert web_client["attributes"]["pkce.code.challenge.method"] == "S256"
    assert web_client["standardFlowEnabled"] is True
    assert web_client["implicitFlowEnabled"] is False
    assert web_client["directAccessGrantsEnabled"] is False
    assert web_client["serviceAccountsEnabled"] is False


def test_web_client_redirects_are_exact(web_client: dict[str, Any]) -> None:
    for uri in web_client["redirectUris"]:
        assert "*" not in uri
    assert "*" not in web_client["attributes"]["post.logout.redirect.uris"]
    assert web_client["webOrigins"] == []


def test_tenant_attribute_is_admin_editable_only(realm: dict[str, Any]) -> None:
    import json

    component = realm["components"]["org.keycloak.userprofile.UserProfileProvider"][0]
    profile = json.loads(component["config"]["kc.user.profile.config"][0])
    tenant = next(a for a in profile["attributes"] if a["name"] == "tenant")
    assert tenant["permissions"]["edit"] == ["admin"]
    assert "unmanagedAttributePolicy" not in profile
