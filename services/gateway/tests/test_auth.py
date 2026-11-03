import base64
import hashlib
import hmac
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from gateway.auth import Principal, require_roles
from gateway.config import Settings
from tests.conftest import EC_KID, RSA_KID, StaticKeySet, TokenFactory, build_app


def _get_me(client: TestClient, token: str) -> tuple[int, dict[str, object]]:
    response = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    return response.status_code, response.json()


def test_missing_token_is_401_with_challenge(client: TestClient) -> None:
    response = client.get("/api/me")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_non_bearer_scheme_is_rejected(client: TestClient) -> None:
    response = client.get("/api/me", headers={"Authorization": "Basic Zm9vOmJhcg=="})
    assert response.status_code == 401


def test_garbage_token_is_401(client: TestClient) -> None:
    status, _ = _get_me(client, "not-a-jwt")
    assert status == 401


@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": int(time.time()) - 3600},
        {"aud": "some-other-api"},
        {"iss": "http://attacker.test/realms/northwind"},
        {"sub": None},
        {"iat": None},
        {"nbf": int(time.time()) + 3600},
        {"typ": "ID"},
        {"typ": None},
    ],
    ids=[
        "expired",
        "wrong-audience",
        "wrong-issuer",
        "missing-sub",
        "missing-iat",
        "not-yet-valid",
        "id-token",
        "missing-typ",
    ],
)
def test_invalid_claims_are_401(
    client: TestClient, make_token: TokenFactory, overrides: dict[str, object]
) -> None:
    status, _ = _get_me(client, make_token(**overrides))
    assert status == 401


def test_token_signed_by_unknown_key_is_401(client: TestClient, make_token: TokenFactory) -> None:
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    status, _ = _get_me(client, make_token(key=other_key))
    assert status == 401


def test_symmetric_algorithm_is_rejected(client: TestClient, make_token: TokenFactory) -> None:
    status, _ = _get_me(
        client, make_token(key="a-shared-secret-of-sufficient-len", algorithm="HS256")
    )
    assert status == 401


def test_unsigned_token_is_rejected(client: TestClient, make_token: TokenFactory) -> None:
    claims = jwt.decode(make_token(), options={"verify_signature": False})
    status, _ = _get_me(client, jwt.encode(claims, None, algorithm="none"))
    assert status == 401


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def test_tampered_payload_is_rejected(client: TestClient, make_token: TokenFactory) -> None:
    header, payload, signature = make_token(roles=["customer"]).split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    claims["realm_access"] = {"roles": ["support_admin"]}
    forged = _b64url(json.dumps(claims).encode())
    status, _ = _get_me(client, f"{header}.{forged}.{signature}")
    assert status == 401


def test_tampered_signature_is_rejected(client: TestClient, make_token: TokenFactory) -> None:
    header, payload, signature = make_token().split(".")
    flipped = ("A" if signature[0] != "A" else "B") + signature[1:]
    status, _ = _get_me(client, f"{header}.{payload}.{flipped}")
    assert status == 401


def test_es256_token_is_accepted(
    client: TestClient, make_token: TokenFactory, ec_signing_key: ec.EllipticCurvePrivateKey
) -> None:
    status, _ = _get_me(client, make_token(key=ec_signing_key, algorithm="ES256", kid=EC_KID))
    assert status == 200


def test_algorithm_must_match_key(
    client: TestClient, make_token: TokenFactory, ec_signing_key: ec.EllipticCurvePrivateKey
) -> None:
    token = make_token(key=ec_signing_key, algorithm="ES256", kid=RSA_KID)
    status, _ = _get_me(client, token)
    assert status == 401


def test_hmac_with_public_key_as_secret_is_rejected(
    client: TestClient, signing_key: rsa.RSAPrivateKey, make_token: TokenFactory
) -> None:
    public_pem = signing_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    claims = jwt.decode(make_token(), options={"verify_signature": False})
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT", "kid": RSA_KID}).encode())
    body = _b64url(json.dumps(claims).encode())
    mac = hmac.new(public_pem, f"{header}.{body}".encode(), hashlib.sha256).digest()
    status, _ = _get_me(client, f"{header}.{body}.{_b64url(mac)}")
    assert status == 401


@pytest.mark.parametrize("kid", [None, "", "unknown-kid"], ids=["missing", "empty", "unknown"])
def test_key_id_must_identify_a_known_key(
    client: TestClient, make_token: TokenFactory, kid: str | None
) -> None:
    status, _ = _get_me(client, make_token(kid=kid))
    assert status == 401


def test_token_without_tenant_is_403(client: TestClient, make_token: TokenFactory) -> None:
    status, body = _get_me(client, make_token(tenant=None))
    assert status == 403
    assert body["detail"] == "token is not bound to a tenant"


def test_unknown_tenant_is_403(client: TestClient, make_token: TokenFactory) -> None:
    status, _ = _get_me(client, make_token(tenant="northwind-legacy"))
    assert status == 403


def test_token_without_application_role_is_403(
    client: TestClient, make_token: TokenFactory
) -> None:
    status, _ = _get_me(client, make_token(roles=["offline_access", "uma_authorization"]))
    assert status == 403


def test_require_roles_rejects_unknown_role_names() -> None:
    with pytest.raises(ValueError):
        require_roles("superuser")


@pytest.fixture
def role_guarded_client(settings: Settings, key_set: StaticKeySet) -> TestClient:
    app: FastAPI = build_app(settings, key_set)

    @app.get("/admin-only")
    async def admin_only(
        principal: Principal = Depends(require_roles("support_admin")),  # noqa: B008
    ) -> dict[str, str]:
        return {"subject": principal.subject}

    return TestClient(app)


@pytest.mark.parametrize(
    ("roles", "expected"),
    [(["customer"], 403), (["support_agent"], 403), (["support_admin"], 200)],
)
def test_require_roles(
    role_guarded_client: TestClient, make_token: TokenFactory, roles: list[str], expected: int
) -> None:
    response = role_guarded_client.get(
        "/admin-only", headers={"Authorization": f"Bearer {make_token(roles=roles)}"}
    )
    assert response.status_code == expected
