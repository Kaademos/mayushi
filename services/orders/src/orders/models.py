import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    MetaData,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

SCHEMA = "orders"

TENANTS = ("northwind-retail", "northwind-b2b")
ORDER_STATUSES = ("placed", "dispatched", "delivered", "cancelled", "returned")
PAYMENT_METHODS = ("card", "paypal", "invoice")
PAYMENT_STATUSES = ("pending", "captured", "voided", "refunded")


def _in(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


class Base(DeclarativeBase):
    metadata = MetaData(
        schema=SCHEMA,
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        },
    )


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("tenant", "email", name="uq_customers_tenant_email"),
        CheckConstraint(_in("tenant", TENANTS), name="tenant"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    tenant: Mapped[str] = mapped_column(String(64), index=True)
    external_ref: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), unique=True)
    email: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    addresses: Mapped[list["Address"]] = relationship(back_populates="customer")


class Address(Base):
    __tablename__ = "addresses"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    line1: Mapped[str] = mapped_column(String(200))
    line2: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(100))
    postcode: Mapped[str] = mapped_column(String(16))
    country: Mapped[str] = mapped_column(String(2), default="GB")
    is_default: Mapped[bool] = mapped_column(default=False)

    customer: Mapped[Customer] = relationship(back_populates="addresses")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(_in("status", ORDER_STATUSES), name="status"),
        CheckConstraint("subtotal_pence >= 0 AND shipping_pence >= 0", name="amounts"),
        CheckConstraint("total_pence = subtotal_pence + shipping_pence", name="total"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    reference: Mapped[str] = mapped_column(String(16), unique=True)
    tenant: Mapped[str] = mapped_column(String(64), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    shipping_address_id: Mapped[int] = mapped_column(ForeignKey("addresses.id"))
    status: Mapped[str] = mapped_column(String(16))
    currency: Mapped[str] = mapped_column(String(3), default="GBP")
    subtotal_pence: Mapped[int]
    shipping_pence: Mapped[int]
    total_pence: Mapped[int]
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    items: Mapped[list["OrderItem"]] = relationship(back_populates="order")
    payments: Mapped[list["Payment"]] = relationship(back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity"),
        CheckConstraint("unit_price_pence >= 0", name="unit_price"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    sku: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[int]
    unit_price_pence: Mapped[int]

    order: Mapped[Order] = relationship(back_populates="items")


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(_in("method", PAYMENT_METHODS), name="method"),
        CheckConstraint(_in("status", PAYMENT_STATUSES), name="status"),
        CheckConstraint("amount_pence >= 0", name="amount"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    method: Mapped[str] = mapped_column(String(16))
    card_brand: Mapped[str | None] = mapped_column(String(16))
    card_last4: Mapped[str | None] = mapped_column(String(4))
    amount_pence: Mapped[int]
    status: Mapped[str] = mapped_column(String(16))
    provider_ref: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    order: Mapped[Order] = relationship(back_populates="payments")
