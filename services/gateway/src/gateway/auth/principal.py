from dataclasses import dataclass

from gateway.tenants import TenantInfo

CUSTOMER = "customer"
SUPPORT_AGENT = "support_agent"
SUPPORT_ADMIN = "support_admin"
KNOWN_ROLES = frozenset({CUSTOMER, SUPPORT_AGENT, SUPPORT_ADMIN})


@dataclass(frozen=True, slots=True)
class Principal:
    subject: str
    username: str
    email: str | None
    name: str | None
    roles: frozenset[str]
    tenant: TenantInfo

    def has_any_role(self, *roles: str) -> bool:
        return not self.roles.isdisjoint(roles)
