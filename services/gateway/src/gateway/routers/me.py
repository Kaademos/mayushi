from fastapi import APIRouter
from pydantic import BaseModel

from gateway.auth import CurrentPrincipal

router = APIRouter(prefix="/api", tags=["identity"])


class TenantOut(BaseModel):
    slug: str
    display_name: str


class MeOut(BaseModel):
    subject: str
    username: str
    email: str | None
    name: str | None
    roles: list[str]
    tenant: TenantOut


@router.get("/me", response_model=MeOut)
async def me(principal: CurrentPrincipal) -> MeOut:
    return MeOut(
        subject=principal.subject,
        username=principal.username,
        email=principal.email,
        name=principal.name,
        roles=sorted(principal.roles),
        tenant=TenantOut(
            slug=principal.tenant.slug,
            display_name=principal.tenant.display_name,
        ),
    )
