import hashlib
import json
from collections import Counter
from typing import Any

from orders.models import ORDER_STATUSES, PAYMENT_METHODS, PAYMENT_STATUSES, TENANTS
from orders.seed import Dataset, build_dataset
from orders.seed.accounts import customer_accounts
from orders.seed.generate import CUSTOMERS_PER_TENANT, MIN_ORDERS_PER_ACCOUNT, ORDER_COUNT

SEED = 20261102


def _digest(data: Dataset) -> str:
    payload: dict[str, Any] = {
        name: getattr(data, name)
        for name in ("customers", "addresses", "orders", "order_items", "payments")
    }
    return hashlib.sha256(json.dumps(payload, default=str, sort_keys=True).encode()).hexdigest()


def test_same_seed_produces_identical_dataset() -> None:
    assert _digest(build_dataset(SEED)) == _digest(build_dataset(SEED))


def test_different_seed_produces_different_dataset() -> None:
    assert _digest(build_dataset(SEED)) != _digest(build_dataset(SEED + 1))


def test_volume() -> None:
    data = build_dataset(SEED)
    assert len(data.customers) == CUSTOMERS_PER_TENANT * len(TENANTS)
    assert len(data.orders) == ORDER_COUNT
    assert len(data.payments) == ORDER_COUNT
    assert Counter(c["tenant"] for c in data.customers) == {
        t: CUSTOMERS_PER_TENANT for t in TENANTS
    }


def test_ids_are_sequential() -> None:
    data = build_dataset(SEED)
    for rows in (data.customers, data.addresses, data.orders, data.order_items, data.payments):
        assert [r["id"] for r in rows] == list(range(1, len(rows) + 1))


def test_orders_are_chronological_by_id() -> None:
    placed = [o["placed_at"] for o in build_dataset(SEED).orders]
    assert placed == sorted(placed)


def test_seeded_accounts_are_linked_and_have_orders() -> None:
    data = build_dataset(SEED)
    by_ref = {c["external_ref"]: c for c in data.customers if c["external_ref"]}
    orders_per_customer = Counter(o["customer_id"] for o in data.orders)
    for account in customer_accounts():
        customer = by_ref[account.external_ref]
        assert customer["email"] == account.email
        assert customer["tenant"] == account.tenant
        assert orders_per_customer[customer["id"]] >= MIN_ORDERS_PER_ACCOUNT


def test_referential_integrity_and_tenant_consistency() -> None:
    data = build_dataset(SEED)
    customers = {c["id"]: c for c in data.customers}
    addresses = {a["id"]: a for a in data.addresses}
    orders = {o["id"]: o for o in data.orders}
    for order in data.orders:
        assert order["tenant"] == customers[order["customer_id"]]["tenant"]
        assert addresses[order["shipping_address_id"]]["customer_id"] == order["customer_id"]
    for item in data.order_items:
        assert item["order_id"] in orders
    defaults = Counter(a["customer_id"] for a in data.addresses if a["is_default"])
    assert all(defaults[customer_id] == 1 for customer_id in customers)


def test_amounts_and_enums_satisfy_schema_constraints() -> None:
    data = build_dataset(SEED)
    orders = {o["id"]: o for o in data.orders}
    item_totals: Counter[int] = Counter()
    for item in data.order_items:
        assert item["quantity"] > 0
        item_totals[item["order_id"]] += item["quantity"] * item["unit_price_pence"]
    for order in data.orders:
        assert order["status"] in ORDER_STATUSES
        assert order["subtotal_pence"] == item_totals[order["id"]]
        assert order["total_pence"] == order["subtotal_pence"] + order["shipping_pence"]
    for payment in data.payments:
        assert payment["method"] in PAYMENT_METHODS
        assert payment["status"] in PAYMENT_STATUSES
        assert payment["amount_pence"] == orders[payment["order_id"]]["total_pence"]
        if payment["method"] == "card":
            assert payment["card_last4"] is not None and len(payment["card_last4"]) == 4
        else:
            assert payment["card_brand"] is None and payment["card_last4"] is None


def test_contact_details_use_reserved_ranges() -> None:
    data = build_dataset(SEED)
    for customer in data.customers:
        domain = customer["email"].rsplit("@", 1)[1]
        assert domain.startswith("example.") or domain.endswith(".example")
        assert customer["phone"].startswith("07700 900")
