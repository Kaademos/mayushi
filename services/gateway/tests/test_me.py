import pytest
from fastapi.testclient import TestClient

from tests.conftest import TokenFactory


def test_me_returns_identity_role_and_tenant(client: TestClient, make_token: TokenFactory) -> None:
    token = make_token(sub="5434558e-35d4-5787-a5ef-5073257fe9fd")
    response = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {
        "subject": "5434558e-35d4-5787-a5ef-5073257fe9fd",
        "username": "kirsty.collins@example.com",
        "email": "kirsty.collins@example.com",
        "name": "Kirsty Collins",
        "roles": ["customer"],
        "tenant": {"slug": "northwind-retail", "display_name": "Northwind Parcel Co. (Retail)"},
    }


@pytest.mark.parametrize(
    ("tenant", "roles"),
    [
        ("northwind-b2b", ["customer"]),
        ("northwind-retail", ["support_agent"]),
        ("northwind-retail", ["support_admin"]),
    ],
)
def test_me_reflects_token_tenant_and_roles(
    client: TestClient, make_token: TokenFactory, tenant: str, roles: list[str]
) -> None:
    token = make_token(tenant=tenant, roles=[*roles, "offline_access"])
    body = client.get("/api/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert body["tenant"]["slug"] == tenant
    assert body["roles"] == roles
