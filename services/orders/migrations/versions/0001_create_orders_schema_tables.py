"""create orders schema tables

Revision ID: 0001
Revises:
Create Date: 2026-11-02 22:14:58.886490
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("tenant", sa.String(length=64), nullable=False),
        sa.Column("external_ref", sa.UUID(), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "tenant IN ('northwind-retail', 'northwind-b2b')", name=op.f("ck_customers_tenant")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customers")),
        sa.UniqueConstraint("external_ref", name=op.f("uq_customers_external_ref")),
        sa.UniqueConstraint("tenant", "email", name="uq_customers_tenant_email"),
        schema="orders",
    )
    op.create_index(
        op.f("ix_customers_tenant"), "customers", ["tenant"], unique=False, schema="orders"
    )
    op.create_table(
        "addresses",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("line1", sa.String(length=200), nullable=False),
        sa.Column("line2", sa.String(length=200), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("postcode", sa.String(length=16), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["orders.customers.id"],
            name=op.f("fk_addresses_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_addresses")),
        schema="orders",
    )
    op.create_index(
        op.f("ix_addresses_customer_id"),
        "addresses",
        ["customer_id"],
        unique=False,
        schema="orders",
    )
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("reference", sa.String(length=16), nullable=False),
        sa.Column("tenant", sa.String(length=64), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("shipping_address_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("subtotal_pence", sa.Integer(), nullable=False),
        sa.Column("shipping_pence", sa.Integer(), nullable=False),
        sa.Column("total_pence", sa.Integer(), nullable=False),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('placed', 'dispatched', 'delivered', 'cancelled', 'returned')",
            name=op.f("ck_orders_status"),
        ),
        sa.CheckConstraint(
            "subtotal_pence >= 0 AND shipping_pence >= 0", name=op.f("ck_orders_amounts")
        ),
        sa.CheckConstraint(
            "total_pence = subtotal_pence + shipping_pence", name=op.f("ck_orders_total")
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["orders.customers.id"], name=op.f("fk_orders_customer_id_customers")
        ),
        sa.ForeignKeyConstraint(
            ["shipping_address_id"],
            ["orders.addresses.id"],
            name=op.f("fk_orders_shipping_address_id_addresses"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orders")),
        sa.UniqueConstraint("reference", name=op.f("uq_orders_reference")),
        schema="orders",
    )
    op.create_index(
        op.f("ix_orders_customer_id"), "orders", ["customer_id"], unique=False, schema="orders"
    )
    op.create_index(
        op.f("ix_orders_placed_at"), "orders", ["placed_at"], unique=False, schema="orders"
    )
    op.create_index(op.f("ix_orders_tenant"), "orders", ["tenant"], unique=False, schema="orders")
    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("sku", sa.String(length=32), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price_pence", sa.Integer(), nullable=False),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_order_items_quantity")),
        sa.CheckConstraint("unit_price_pence >= 0", name=op.f("ck_order_items_unit_price")),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.orders.id"],
            name=op.f("fk_order_items_order_id_orders"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_items")),
        schema="orders",
    )
    op.create_index(
        op.f("ix_order_items_order_id"), "order_items", ["order_id"], unique=False, schema="orders"
    )
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("card_brand", sa.String(length=16), nullable=True),
        sa.Column("card_last4", sa.String(length=4), nullable=True),
        sa.Column("amount_pence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("provider_ref", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "method IN ('card', 'paypal', 'invoice')", name=op.f("ck_payments_method")
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'captured', 'voided', 'refunded')",
            name=op.f("ck_payments_status"),
        ),
        sa.CheckConstraint("amount_pence >= 0", name=op.f("ck_payments_amount")),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.orders.id"],
            name=op.f("fk_payments_order_id_orders"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
        sa.UniqueConstraint("provider_ref", name=op.f("uq_payments_provider_ref")),
        schema="orders",
    )
    op.create_index(
        op.f("ix_payments_order_id"), "payments", ["order_id"], unique=False, schema="orders"
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_payments_order_id"), table_name="payments", schema="orders")
    op.drop_table("payments", schema="orders")
    op.drop_index(op.f("ix_order_items_order_id"), table_name="order_items", schema="orders")
    op.drop_table("order_items", schema="orders")
    op.drop_index(op.f("ix_orders_tenant"), table_name="orders", schema="orders")
    op.drop_index(op.f("ix_orders_placed_at"), table_name="orders", schema="orders")
    op.drop_index(op.f("ix_orders_customer_id"), table_name="orders", schema="orders")
    op.drop_table("orders", schema="orders")
    op.drop_index(op.f("ix_addresses_customer_id"), table_name="addresses", schema="orders")
    op.drop_table("addresses", schema="orders")
    op.drop_index(op.f("ix_customers_tenant"), table_name="customers", schema="orders")
    op.drop_table("customers", schema="orders")
