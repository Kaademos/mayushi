from dataclasses import dataclass
from typing import Annotated, Protocol

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.db import get_session
from gateway.models import Tenant


@dataclass(frozen=True, slots=True)
class TenantInfo:
    slug: str
    display_name: str


class TenantDirectory(Protocol):
    async def get_active(self, slug: str) -> TenantInfo | None: ...


class SqlTenantDirectory:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active(self, slug: str) -> TenantInfo | None:
        tenant = await self._session.scalar(
            select(Tenant).where(Tenant.slug == slug, Tenant.is_active.is_(True))
        )
        if tenant is None:
            return None
        return TenantInfo(slug=tenant.slug, display_name=tenant.display_name)


def get_tenant_directory(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TenantDirectory:
    return SqlTenantDirectory(session)
