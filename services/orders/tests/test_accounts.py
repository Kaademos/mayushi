import json
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from orders.seed.accounts import SEEDED_ACCOUNTS

REALM_EXPORT = Path(__file__).resolve().parents[3] / "infra" / "keycloak" / "realm-northwind.json"


@pytest.fixture(scope="module")
def realm_users() -> dict[uuid.UUID, dict[str, Any]]:
    realm = json.loads(REALM_EXPORT.read_text())
    return {uuid.UUID(u["id"]): u for u in realm["users"]}


def test_every_seeded_account_exists_in_realm(realm_users: dict[uuid.UUID, Any]) -> None:
    assert set(realm_users) == {a.external_ref for a in SEEDED_ACCOUNTS}
    for account in SEEDED_ACCOUNTS:
        user = realm_users[account.external_ref]
        assert user["username"] == account.email
        assert user["email"] == account.email
        assert user["firstName"] == account.first_name
        assert user["lastName"] == account.last_name
        assert user["attributes"]["tenant"] == [account.tenant]
        assert user["realmRoles"] == [account.role]


def test_account_mix() -> None:
    customers = Counter(a.tenant for a in SEEDED_ACCOUNTS if a.role == "customer")
    assert customers == {"northwind-retail": 3, "northwind-b2b": 3}
    roles = Counter(a.role for a in SEEDED_ACCOUNTS)
    assert roles["support_agent"] == 1
    assert roles["support_admin"] == 1
