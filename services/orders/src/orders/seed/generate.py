"""Deterministic synthetic dataset for the orders schema.

Everything is derived from a single integer seed and a fixed reference date, so the
same seed always yields byte-identical rows (including primary keys).
"""

import random
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from faker import Faker

from orders.models import TENANTS
from orders.seed.accounts import customer_accounts

REFERENCE_DATE = datetime(2026, 10, 31, 18, 0, tzinfo=UTC)
HISTORY_DAYS = 540
CUSTOMERS_PER_TENANT = 40
ORDER_COUNT = 200
MIN_ORDERS_PER_ACCOUNT = 4
FREE_SHIPPING_THRESHOLD_PENCE = 5000
SHIPPING_PENCE = 399

EMAIL_DOMAINS = ("example.com", "example.net", "example.org")

# (sku, description, unit price in pence)
CATALOGUE: tuple[tuple[str, str, int], ...] = (
    ("NW-BOX-S10", "Small shipping boxes (pack of 10)", 899),
    ("NW-BOX-M10", "Medium shipping boxes (pack of 10)", 1299),
    ("NW-BOX-L10", "Large shipping boxes (pack of 10)", 1799),
    ("NW-TAPE-6", "Parcel tape, 48mm (6 rolls)", 749),
    ("NW-MAIL-50", "Padded mailers A4 (pack of 50)", 2199),
    ("NW-BUBL-50", "Bubble wrap roll, 50m", 2499),
    ("NW-LBL-500", "Thermal shipping labels (500)", 1599),
    ("NW-PRN-T1", "Thermal label printer", 11999),
    ("NW-SCL-30", "Parcel scale, 30kg", 3499),
    ("NW-FILL-1", "Biodegradable void fill (1 sack)", 1099),
    ("NW-DISP-1", "Tape dispenser gun", 1499),
    ("NW-POST-25", "Postal tubes (pack of 25)", 1899),
)
CARD_BRANDS = ("visa", "mastercard", "amex")


@dataclass(slots=True)
class Dataset:
    customers: list[dict[str, Any]] = field(default_factory=list)
    addresses: list[dict[str, Any]] = field(default_factory=list)
    orders: list[dict[str, Any]] = field(default_factory=list)
    order_items: list[dict[str, Any]] = field(default_factory=list)
    payments: list[dict[str, Any]] = field(default_factory=list)


def _status_for(placed_at: datetime, rng: random.Random) -> str:
    age = REFERENCE_DATE - placed_at
    if rng.random() < 0.04:
        return "cancelled"
    if age < timedelta(days=2):
        return "placed"
    if age < timedelta(days=6):
        return "dispatched"
    if rng.random() < 0.05:
        return "returned"
    return "delivered"


def _payment_status(order_status: str) -> str:
    return {
        "placed": "pending",
        "cancelled": "voided",
        "returned": "refunded",
    }.get(order_status, "captured")


def build_dataset(seed: int) -> Dataset:
    fake = Faker("en_GB")
    fake.seed_instance(seed)
    rng = random.Random(seed)
    data = Dataset()

    accounts_by_tenant = {
        tenant: [a for a in customer_accounts() if a.tenant == tenant] for tenant in TENANTS
    }
    default_address: dict[int, int] = {}
    customer_ids_by_tenant: dict[str, list[int]] = {tenant: [] for tenant in TENANTS}
    account_customer_ids: list[int] = []

    for tenant in TENANTS:
        accounts = accounts_by_tenant[tenant]
        for index in range(CUSTOMERS_PER_TENANT):
            customer_id = len(data.customers) + 1
            if index < len(accounts):
                account = accounts[index]
                full_name, email = account.full_name, account.email
                external_ref: uuid.UUID | None = account.external_ref
                account_customer_ids.append(customer_id)
            else:
                first, last = fake.first_name(), fake.last_name()
                full_name = f"{first} {last}"
                domain = rng.choice(EMAIL_DOMAINS)
                email = f"{first}.{last}{customer_id}@{domain}".lower().replace("'", "")
                external_ref = None
            created_at = REFERENCE_DATE - timedelta(
                days=HISTORY_DAYS + rng.randint(1, 365), minutes=rng.randint(0, 1439)
            )
            data.customers.append(
                {
                    "id": customer_id,
                    "tenant": tenant,
                    "external_ref": external_ref,
                    "email": email,
                    "full_name": full_name,
                    # Ofcom-reserved drama range: never a real subscriber number.
                    "phone": f"07700 900{rng.randint(0, 999):03d}",
                    "created_at": created_at,
                }
            )
            customer_ids_by_tenant[tenant].append(customer_id)

            for address_index in range(rng.choice((1, 1, 2))):
                address_id = len(data.addresses) + 1
                data.addresses.append(
                    {
                        "id": address_id,
                        "customer_id": customer_id,
                        "line1": fake.street_address(),
                        "line2": None if rng.random() < 0.7 else fake.secondary_address(),
                        "city": fake.city(),
                        "postcode": fake.postcode(),
                        "country": "GB",
                        "is_default": address_index == 0,
                    }
                )
                if address_index == 0:
                    default_address[customer_id] = address_id

    customer_tenant = {c["id"]: c["tenant"] for c in data.customers}
    owners = [cid for cid in account_customer_ids for _ in range(MIN_ORDERS_PER_ACCOUNT)]
    all_customer_ids = [c["id"] for c in data.customers]
    owners += [rng.choice(all_customer_ids) for _ in range(ORDER_COUNT - len(owners))]

    drafts = []
    for owner in owners:
        placed_at = REFERENCE_DATE - timedelta(
            days=rng.randint(0, HISTORY_DAYS), seconds=rng.randint(0, 86399)
        )
        drafts.append((placed_at, owner))
    drafts.sort()

    for placed_at, customer_id in drafts:
        order_id = len(data.orders) + 1
        tenant = customer_tenant[customer_id]
        bulk = tenant == "northwind-b2b"
        subtotal = 0
        for sku, description, price in rng.sample(CATALOGUE, rng.randint(1, 4)):
            quantity = rng.randint(5, 40) if bulk else rng.randint(1, 3)
            subtotal += quantity * price
            data.order_items.append(
                {
                    "id": len(data.order_items) + 1,
                    "order_id": order_id,
                    "sku": sku,
                    "description": description,
                    "quantity": quantity,
                    "unit_price_pence": price,
                }
            )
        shipping = 0 if subtotal >= FREE_SHIPPING_THRESHOLD_PENCE else SHIPPING_PENCE
        status = _status_for(placed_at, rng)
        data.orders.append(
            {
                "id": order_id,
                "reference": f"NWP-{100000 + order_id}",
                "tenant": tenant,
                "customer_id": customer_id,
                "shipping_address_id": default_address[customer_id],
                "status": status,
                "currency": "GBP",
                "subtotal_pence": subtotal,
                "shipping_pence": shipping,
                "total_pence": subtotal + shipping,
                "placed_at": placed_at,
            }
        )

        if bulk and rng.random() < 0.6:
            method = "invoice"
        else:
            method = "card" if rng.random() < 0.8 else "paypal"
        data.payments.append(
            {
                "id": len(data.payments) + 1,
                "order_id": order_id,
                "method": method,
                "card_brand": rng.choice(CARD_BRANDS) if method == "card" else None,
                "card_last4": f"{rng.randint(0, 9999):04d}" if method == "card" else None,
                "amount_pence": subtotal + shipping,
                "status": _payment_status(status),
                "provider_ref": f"pay_{rng.getrandbits(64):016x}",
                "created_at": placed_at + timedelta(seconds=rng.randint(5, 120)),
            }
        )

    return data
