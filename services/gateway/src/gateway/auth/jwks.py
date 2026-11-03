"""Cached JSON Web Key Set with bounded refresh.

Keys are refreshed when the cache is older than `ttl_seconds`, and on an unknown `kid`
(key rotation), but never more often than `min_refresh_interval_seconds`, so a flood of
tokens with random `kid` values cannot turn into a flood of requests to the IdP.
"""

import json
import logging
import threading
import time
import urllib.request
from collections.abc import Callable
from typing import Any, Protocol

import jwt

from gateway.auth.errors import TokenError

logger = logging.getLogger(__name__)

SIGNING_KEY_TYPES = frozenset({"RSA", "EC"})

JwksFetcher = Callable[[], dict[str, Any]]


class KeySet(Protocol):
    def get(self, kid: str) -> jwt.PyJWK: ...


def http_jwks_fetcher(url: str, *, timeout: float = 5.0) -> JwksFetcher:
    def fetch() -> dict[str, Any]:
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data: dict[str, Any] = json.load(response)
        return data

    return fetch


def parse_signing_keys(document: dict[str, Any]) -> dict[str, jwt.PyJWK]:
    keys: dict[str, jwt.PyJWK] = {}
    for entry in document.get("keys", []):
        if not isinstance(entry, dict):
            continue
        kid = entry.get("kid")
        if not isinstance(kid, str) or entry.get("use", "sig") != "sig":
            continue
        if entry.get("kty") not in SIGNING_KEY_TYPES:
            continue
        try:
            keys[kid] = jwt.PyJWK(entry)
        except jwt.PyJWKError:
            logger.warning("ignoring unusable JWK kid=%s", kid)
    return keys


class CachedJwks:
    def __init__(
        self,
        fetch: JwksFetcher,
        *,
        ttl_seconds: float = 300,
        min_refresh_interval_seconds: float = 30,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fetch = fetch
        self._ttl = ttl_seconds
        self._min_interval = min_refresh_interval_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at: float | None = None
        self._last_attempt: float | None = None

    def get(self, kid: str) -> jwt.PyJWK:
        with self._lock:
            now = self._clock()
            if self._fetched_at is None or now - self._fetched_at >= self._ttl:
                self._refresh(now)
            key = self._keys.get(kid)
            if key is None and self._may_refresh(now):
                self._refresh(now)
                key = self._keys.get(kid)
        if key is None:
            raise TokenError("unknown signing key")
        return key

    def _may_refresh(self, now: float) -> bool:
        return self._last_attempt is None or now - self._last_attempt >= self._min_interval

    def _refresh(self, now: float) -> None:
        if not self._may_refresh(now):
            return
        self._last_attempt = now
        try:
            keys = parse_signing_keys(self._fetch())
        except Exception as exc:
            if self._keys:
                logger.warning("JWKS refresh failed, keeping cached keys: %s", exc)
                return
            raise TokenError("signing keys unavailable") from exc
        self._keys = keys
        self._fetched_at = now
