from collections.abc import Iterable
from typing import Any

import anyio.to_thread
import jwt

from gateway.auth.errors import TokenError
from gateway.auth.jwks import KeySet

REQUIRED_CLAIMS = ("exp", "iat", "iss", "aud", "sub")
ACCESS_TOKEN_TYPE = "Bearer"


class TokenVerifier:
    """Validates IdP-issued access tokens for this API.

    Pins issuer, audience and the asymmetric algorithms allowed; the header `alg` must
    match the algorithm of the JWK selected by `kid`. `exp`, `iat` and `nbf` (when present)
    are checked with a small leeway, and ID tokens are rejected via the `typ` claim.
    """

    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        key_set: KeySet,
        algorithms: Iterable[str] = ("RS256", "ES256"),
        leeway_seconds: int = 30,
    ) -> None:
        self._issuer = issuer
        self._audience = audience
        self._key_set = key_set
        self._algorithms = frozenset(algorithms)
        self._leeway = leeway_seconds

    def verify(self, token: str) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.DecodeError as exc:
            raise TokenError("malformed token") from exc

        algorithm = header.get("alg")
        if algorithm not in self._algorithms:
            raise TokenError("unsupported signing algorithm")
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise TokenError("token has no key id")

        jwk = self._key_set.get(kid)
        if jwk.algorithm_name != algorithm:
            raise TokenError("algorithm does not match signing key")

        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                jwk.key,
                algorithms=[algorithm],
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway,
                options={"require": list(REQUIRED_CLAIMS), "verify_nbf": True},
            )
        except jwt.InvalidTokenError as exc:
            raise TokenError(str(exc)) from exc

        if claims.get("typ") != ACCESS_TOKEN_TYPE:
            raise TokenError("not an access token")
        return claims

    async def verify_async(self, token: str) -> dict[str, Any]:
        # A cache miss fetches JWKS over the network; keep it off the event loop.
        return await anyio.to_thread.run_sync(self.verify, token)
