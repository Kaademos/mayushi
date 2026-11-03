from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from gateway.auth import CachedJwks, TokenError
from tests.conftest import public_jwk


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class FakeIdp:
    def __init__(self, *keys: dict[str, Any]) -> None:
        self.keys = list(keys)
        self.calls = 0
        self.fail = False

    def __call__(self) -> dict[str, Any]:
        self.calls += 1
        if self.fail:
            raise OSError("connection refused")
        return {"keys": self.keys}


@pytest.fixture
def rsa_jwk() -> dict[str, Any]:
    return public_jwk(rsa.generate_private_key(public_exponent=65537, key_size=2048), "k1")


@pytest.fixture
def rotated_jwk() -> dict[str, Any]:
    return public_jwk(ec.generate_private_key(ec.SECP256R1()), "k2")


def _cache(idp: FakeIdp, clock: FakeClock) -> CachedJwks:
    return CachedJwks(idp, ttl_seconds=300, min_refresh_interval_seconds=30, clock=clock)


def test_keys_are_cached_within_ttl(rsa_jwk: dict[str, Any]) -> None:
    idp, clock = FakeIdp(rsa_jwk), FakeClock()
    cache = _cache(idp, clock)
    for _ in range(5):
        assert cache.get("k1").algorithm_name == "RS256"
    assert idp.calls == 1


def test_rotation_picks_up_new_kid(rsa_jwk: dict[str, Any], rotated_jwk: dict[str, Any]) -> None:
    idp, clock = FakeIdp(rsa_jwk), FakeClock()
    cache = _cache(idp, clock)
    cache.get("k1")
    idp.keys.append(rotated_jwk)
    clock.now += 31
    assert cache.get("k2").algorithm_name == "ES256"
    assert idp.calls == 2


def test_unknown_kid_flood_is_rate_limited(rsa_jwk: dict[str, Any]) -> None:
    idp, clock = FakeIdp(rsa_jwk), FakeClock()
    cache = _cache(idp, clock)
    cache.get("k1")
    for i in range(100):
        with pytest.raises(TokenError):
            cache.get(f"attacker-{i}")
    assert idp.calls == 1
    clock.now += 31
    with pytest.raises(TokenError):
        cache.get("attacker-x")
    assert idp.calls == 2


def test_cache_refreshes_after_ttl(rsa_jwk: dict[str, Any]) -> None:
    idp, clock = FakeIdp(rsa_jwk), FakeClock()
    cache = _cache(idp, clock)
    cache.get("k1")
    clock.now += 301
    cache.get("k1")
    assert idp.calls == 2


def test_removed_key_stops_validating_after_ttl(rsa_jwk: dict[str, Any]) -> None:
    idp, clock = FakeIdp(rsa_jwk), FakeClock()
    cache = _cache(idp, clock)
    cache.get("k1")
    idp.keys.clear()
    clock.now += 301
    with pytest.raises(TokenError):
        cache.get("k1")


def test_idp_outage_keeps_serving_cached_keys(rsa_jwk: dict[str, Any]) -> None:
    idp, clock = FakeIdp(rsa_jwk), FakeClock()
    cache = _cache(idp, clock)
    cache.get("k1")
    idp.fail = True
    clock.now += 301
    assert cache.get("k1").algorithm_name == "RS256"


def test_idp_unavailable_without_cache_fails_closed() -> None:
    idp, clock = FakeIdp(), FakeClock()
    idp.fail = True
    with pytest.raises(TokenError):
        _cache(idp, clock).get("k1")


@pytest.mark.parametrize(
    "mutation",
    [{"use": "enc"}, {"kty": "oct", "k": "c2VjcmV0"}, {"kid": None}],
    ids=["encryption-key", "symmetric-key", "no-kid"],
)
def test_non_signing_keys_are_ignored(rsa_jwk: dict[str, Any], mutation: dict[str, Any]) -> None:
    entry = {**rsa_jwk, **mutation}
    idp, clock = FakeIdp(entry), FakeClock()
    with pytest.raises(TokenError):
        _cache(idp, clock).get("k1")
