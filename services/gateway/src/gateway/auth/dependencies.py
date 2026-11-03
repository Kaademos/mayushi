import logging
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from gateway.auth.errors import TokenError
from gateway.auth.principal import KNOWN_ROLES, Principal
from gateway.auth.tokens import TokenVerifier
from gateway.tenants import TenantDirectory, get_tenant_directory

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_token_verifier(request: Request) -> TokenVerifier:
    verifier: TokenVerifier = request.app.state.token_verifier
    return verifier


def _realm_roles(claims: dict[str, Any]) -> frozenset[str]:
    realm_access = claims.get("realm_access")
    if not isinstance(realm_access, dict):
        return frozenset()
    roles = realm_access.get("roles")
    if not isinstance(roles, list):
        return frozenset()
    return frozenset(r for r in roles if isinstance(r, str)) & KNOWN_ROLES


async def get_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    verifier: Annotated[TokenVerifier, Depends(get_token_verifier)],
    tenants: Annotated[TenantDirectory, Depends(get_tenant_directory)],
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized("missing bearer token")

    try:
        claims = await verifier.verify_async(credentials.credentials)
    except TokenError as exc:
        logger.info("rejected bearer token: %s", exc)
        raise _unauthorized("invalid token") from exc

    tenant_slug = claims.get("tenant")
    if not isinstance(tenant_slug, str) or not tenant_slug:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "token is not bound to a tenant")
    tenant = await tenants.get_active(tenant_slug)
    if tenant is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "unknown or inactive tenant")

    roles = _realm_roles(claims)
    if not roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "no application role assigned")

    return Principal(
        subject=claims["sub"],
        username=claims.get("preferred_username") or claims["sub"],
        email=claims.get("email"),
        name=claims.get("name"),
        roles=roles,
        tenant=tenant,
    )


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


def require_roles(*roles: str) -> Callable[[Principal], Awaitable[Principal]]:
    unknown = set(roles) - KNOWN_ROLES
    if unknown:
        raise ValueError(f"unknown roles: {sorted(unknown)}")

    async def dependency(principal: CurrentPrincipal) -> Principal:
        if not principal.has_any_role(*roles):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient role")
        return principal

    return dependency
