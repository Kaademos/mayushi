"""Identities that also exist as users in the Keycloak realm export.

`external_ref` is the Keycloak user id (`sub` claim). Keep this list in sync with
`infra/keycloak/realm-northwind.json`; `tests/test_accounts.py` enforces it.
"""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SeededAccount:
    external_ref: uuid.UUID
    email: str
    first_name: str
    last_name: str
    tenant: str
    role: str

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


SEEDED_ACCOUNTS: tuple[SeededAccount, ...] = (
    SeededAccount(
        uuid.UUID("5434558e-35d4-5787-a5ef-5073257fe9fd"),
        "kirsty.collins@example.com",
        "Kirsty",
        "Collins",
        "northwind-retail",
        "customer",
    ),
    SeededAccount(
        uuid.UUID("1146803c-9191-5e6d-9b59-f3e749298c56"),
        "gemma.yates@example.net",
        "Gemma",
        "Yates",
        "northwind-retail",
        "customer",
    ),
    SeededAccount(
        uuid.UUID("e5314e72-30b3-5eb2-b9f6-618240bcd30d"),
        "sam.blake@example.org",
        "Sam",
        "Blake",
        "northwind-retail",
        "customer",
    ),
    SeededAccount(
        uuid.UUID("7c24345a-3678-5343-ac6e-b9104e4f7857"),
        "samuel.carter@example.com",
        "Samuel",
        "Carter",
        "northwind-b2b",
        "customer",
    ),
    SeededAccount(
        uuid.UUID("44e94a58-2c56-5481-8c17-c31c10c3a3e4"),
        "francesca.howell@example.net",
        "Francesca",
        "Howell",
        "northwind-b2b",
        "customer",
    ),
    SeededAccount(
        uuid.UUID("3cea333a-2cb4-5f9a-956a-f7226f1f487e"),
        "carol.turner@example.org",
        "Carol",
        "Turner",
        "northwind-b2b",
        "customer",
    ),
    SeededAccount(
        uuid.UUID("36e5ed16-8896-576d-afaa-26955cd4bb05"),
        "amber.jones@northwindparcel.example",
        "Amber",
        "Jones",
        "northwind-retail",
        "support_agent",
    ),
    SeededAccount(
        uuid.UUID("b7d4edc3-d592-5d2a-b091-492d09cfeec7"),
        "alex.coles@northwindparcel.example",
        "Alex",
        "Coles",
        "northwind-retail",
        "support_admin",
    ),
)


def customer_accounts() -> tuple[SeededAccount, ...]:
    return tuple(a for a in SEEDED_ACCOUNTS if a.role == "customer")
