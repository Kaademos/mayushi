import json
import time
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway.auth import TokenError, TokenVerifier
from gateway.config import Settings
from gateway.main import create_app
from gateway.tenants import TenantInfo, get_tenant_directory

ISSUER = "http://keycloak.test/realms/northwind"
AUDIENCE = "mayushi-api"
RSA_KID = "rsa-1"
EC_KID = "ec-1"

TokenFactory = Callable[..., str]


class FakeTenantDirectory:
    def __init__(self, tenants: dict[str, TenantInfo]) -> None:
        self._tenants = tenants

    async def get_active(self, slug: str) -> TenantInfo | None:
        return self._tenants.get(slug)


class StaticKeySet:
    def __init__(self, keys: dict[str, jwt.PyJWK]) -> None:
        self._keys = keys

    def get(self, kid: str) -> jwt.PyJWK:
        try:
            return self._keys[kid]
        except KeyError:
            raise TokenError("unknown signing key") from None


TENANTS = {
    "northwind-retail": TenantInfo("northwind-retail", "Northwind Parcel Co. (Retail)"),
    "northwind-b2b": TenantInfo("northwind-b2b", "Northwind Parcel Co. (Business)"),
}


def public_jwk(key: rsa.RSAPrivateKey | ec.EllipticCurvePrivateKey, kid: str) -> dict[str, Any]:
    if isinstance(key, rsa.RSAPrivateKey):
        data = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
        alg = "RS256"
    else:
        data = jwt.algorithms.ECAlgorithm.to_jwk(key.public_key(), as_dict=True)
        alg = "ES256"
    return {**json.loads(json.dumps(data)), "kid": kid, "use": "sig", "alg": alg}


@pytest.fixture(scope="session")
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def ec_signing_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture(scope="session")
def key_set(
    signing_key: rsa.RSAPrivateKey, ec_signing_key: ec.EllipticCurvePrivateKey
) -> StaticKeySet:
    return StaticKeySet(
        {
            RSA_KID: jwt.PyJWK(public_jwk(signing_key, RSA_KID)),
            EC_KID: jwt.PyJWK(public_jwk(ec_signing_key, EC_KID)),
        }
    )


@pytest.fixture
def settings() -> Settings:
    return Settings(
        ENV="development",
        oidc_issuer=ISSUER,
        oidc_audience=AUDIENCE,
        oidc_jwks_url="http://keycloak.test/certs",
    )


@pytest.fixture
def make_token(signing_key: rsa.RSAPrivateKey) -> TokenFactory:
    def factory(
        *,
        roles: list[str] | None = None,
        tenant: str | None = "northwind-retail",
        key: Any = None,
        algorithm: str = "RS256",
        kid: str | None = RSA_KID,
        **overrides: Any,
    ) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": ISSUER,
            "aud": [AUDIENCE, "account"],
            "sub": str(uuid.uuid4()),
            "typ": "Bearer",
            "iat": now,
            "exp": now + 300,
            "preferred_username": "kirsty.collins@example.com",
            "email": "kirsty.collins@example.com",
            "name": "Kirsty Collins",
            "realm_access": {"roles": roles if roles is not None else ["customer"]},
        }
        if tenant is not None:
            claims["tenant"] = tenant
        claims.update(overrides)
        claims = {k: v for k, v in claims.items() if v is not None}
        headers = {"kid": kid} if kid is not None else {}
        return jwt.encode(claims, key or signing_key, algorithm=algorithm, headers=headers)

    return factory


def build_app(settings: Settings, key_set: StaticKeySet) -> FastAPI:
    verifier = TokenVerifier(issuer=ISSUER, audience=AUDIENCE, key_set=key_set)
    app = create_app(settings, token_verifier=verifier)
    app.dependency_overrides[get_tenant_directory] = lambda: FakeTenantDirectory(TENANTS)
    return app


@pytest.fixture
def app(settings: Settings, key_set: StaticKeySet) -> FastAPI:
    return build_app(settings, key_set)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
