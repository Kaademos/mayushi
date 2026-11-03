"""End-to-end login against the running stack (`make up && make seed`).

Drives Keycloak's hosted login page with the authorisation-code + PKCE flow used by
the web app, exchanges the code for tokens, then calls the gateway with the access token.
"""

import base64
import hashlib
import html
import json
import os
import re
import secrets
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

pytestmark = pytest.mark.integration

KEYCLOAK_URL = os.environ.get("KEYCLOAK_PUBLIC_URL", "http://localhost:8080")
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8000")
REALM = "northwind"
CLIENT_ID = "mayushi-web"
REDIRECT_URI = "http://localhost:3000/auth/callback"
DEMO_PASSWORD = os.environ.get("DEMO_USER_PASSWORD", "")
WEB_CLIENT_SECRET = os.environ.get("WEB_CLIENT_SECRET", "")

if not DEMO_PASSWORD or not WEB_CLIENT_SECRET:
    pytest.skip(
        "DEMO_USER_PASSWORD and WEB_CLIENT_SECRET must be set (run via `make test-integration`)",
        allow_module_level=True,
    )

REALM_EXPORT = Path(__file__).resolve().parents[4] / "infra" / "keycloak" / "realm-northwind.json"
REALM_USERS: list[dict[str, Any]] = json.loads(REALM_EXPORT.read_text())["users"]

_FORM_ACTION = re.compile(r'<form[^>]+id="kc-form-login"[^>]+action="([^"]+)"')


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def _accept_localhost_secure_cookies(browser: httpx.Client) -> None:
    # Browsers treat http://localhost as a secure context and send `Secure` cookies to it;
    # httpx does not, so mirror that behaviour for the local stack only.
    for cookie in browser.cookies.jar:
        if cookie.domain in ("localhost", "localhost.local", "127.0.0.1"):
            cookie.secure = False


def _oidc_url(endpoint: str) -> str:
    return f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/{endpoint}"


def _authorize(
    browser: httpx.Client,
    username: str,
    password: str,
    challenge: str,
    *,
    redirect_uri: str = REDIRECT_URI,
) -> httpx.Response:
    """Submit Keycloak's login form; returns the response to the credential POST."""
    page = browser.get(
        _oidc_url("auth"),
        params={
            "client_id": CLIENT_ID,
            "response_type": "code",
            "scope": "openid profile email",
            "redirect_uri": redirect_uri,
            "state": "test-state",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
    )
    page.raise_for_status()
    _accept_localhost_secure_cookies(browser)
    match = _FORM_ACTION.search(page.text)
    assert match, "Keycloak login form not found"
    return browser.post(
        html.unescape(match.group(1)),
        data={"username": username, "password": password, "credentialId": ""},
        follow_redirects=False,
    )


def _authorization_code(browser: httpx.Client, username: str, password: str, challenge: str) -> str:
    submitted = _authorize(browser, username, password, challenge)
    assert submitted.status_code == 302, f"login failed for {username}"
    callback = urlparse(submitted.headers["location"])
    assert callback.geturl().startswith(REDIRECT_URI)
    params = parse_qs(callback.query)
    assert params["state"] == ["test-state"]
    return params["code"][0]


def _exchange(
    code: str, verifier: str, *, client_secret: str | None = WEB_CLIENT_SECRET
) -> httpx.Response:
    data = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": verifier,
    }
    if client_secret is not None:
        data["client_secret"] = client_secret
    return httpx.post(_oidc_url("token"), data=data, timeout=10)


def login(username: str, password: str) -> dict[str, Any]:
    verifier, challenge = _pkce_pair()
    with httpx.Client(timeout=10, follow_redirects=True) as browser:
        code = _authorization_code(browser, username, password, challenge)
    tokens = _exchange(code, verifier)
    tokens.raise_for_status()
    result: dict[str, Any] = tokens.json()
    return result


def _fresh_code() -> tuple[str, str]:
    verifier, challenge = _pkce_pair()
    with httpx.Client(timeout=10, follow_redirects=True) as browser:
        code = _authorization_code(browser, REALM_USERS[0]["username"], DEMO_PASSWORD, challenge)
    return code, verifier


@pytest.mark.parametrize("user", REALM_USERS, ids=[u["username"] for u in REALM_USERS])
def test_seeded_user_can_log_in_and_see_role_and_tenant(user: dict[str, Any]) -> None:
    tokens = login(user["username"], DEMO_PASSWORD)

    response = httpx.get(
        f"{GATEWAY_URL}/api/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        timeout=10,
    )
    assert response.status_code == 200, response.text
    me = response.json()
    assert me["subject"] == user["id"]
    assert me["username"] == user["username"]
    assert me["roles"] == user["realmRoles"]
    assert me["tenant"]["slug"] == user["attributes"]["tenant"][0]


def test_wrong_password_is_rejected() -> None:
    _, challenge = _pkce_pair()
    with httpx.Client(timeout=10, follow_redirects=True) as browser:
        response = _authorize(browser, REALM_USERS[0]["username"], "not-the-password", challenge)
    assert response.status_code != 302


def test_code_exchange_requires_matching_pkce_verifier() -> None:
    code, verifier = _fresh_code()
    assert _exchange(code, "wrong-" + verifier).status_code == 400


@pytest.mark.parametrize("secret", [None, "not-the-client-secret"], ids=["missing", "wrong"])
def test_code_exchange_requires_client_secret(secret: str | None) -> None:
    code, verifier = _fresh_code()
    assert _exchange(code, verifier, client_secret=secret).status_code in (400, 401)


def test_unregistered_redirect_uri_is_refused() -> None:
    _, challenge = _pkce_pair()
    with httpx.Client(timeout=10, follow_redirects=True) as browser:
        page = browser.get(
            _oidc_url("auth"),
            params={
                "client_id": CLIENT_ID,
                "response_type": "code",
                "scope": "openid",
                "redirect_uri": "http://localhost:3000/somewhere-else",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
        )
    assert page.status_code == 400
    assert _FORM_ACTION.search(page.text) is None


def test_refresh_tokens_are_single_use() -> None:
    tokens = login(REALM_USERS[0]["username"], DEMO_PASSWORD)
    refresh = {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "client_secret": WEB_CLIENT_SECRET,
        "refresh_token": tokens["refresh_token"],
    }
    first = httpx.post(_oidc_url("token"), data=refresh, timeout=10)
    assert first.status_code == 200
    assert first.json()["refresh_token"] != tokens["refresh_token"]
    replay = httpx.post(_oidc_url("token"), data=refresh, timeout=10)
    assert replay.status_code == 400


def test_access_token_lifetime_is_short() -> None:
    tokens = login(REALM_USERS[0]["username"], DEMO_PASSWORD)
    assert tokens["expires_in"] <= 300


def test_password_grant_is_disabled() -> None:
    response = httpx.post(
        _oidc_url("token"),
        data={
            "grant_type": "password",
            "client_id": CLIENT_ID,
            "client_secret": WEB_CLIENT_SECRET,
            "username": REALM_USERS[0]["username"],
            "password": DEMO_PASSWORD,
        },
        timeout=10,
    )
    assert response.status_code in (400, 401)
