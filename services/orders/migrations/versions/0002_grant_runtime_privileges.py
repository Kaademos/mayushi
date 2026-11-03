"""grant runtime privileges to orders_svc

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-03 10:30:00

The runtime role gets DML on business tables only: no DDL, no TRUNCATE, and no access
to the Alembic version table. Every later migration that adds a table must grant it here
explicitly (deny by default); tests/security asserts the resulting privilege matrix.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNTIME_ROLE = "orders_svc"
TABLES = ("customers", "addresses", "orders", "order_items", "payments")


def upgrade() -> None:
    op.execute(f"GRANT USAGE ON SCHEMA orders TO {RUNTIME_ROLE}")
    for table in TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON orders.{table} TO {RUNTIME_ROLE}")
        op.execute(f"GRANT USAGE, SELECT ON SEQUENCE orders.{table}_id_seq TO {RUNTIME_ROLE}")


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"REVOKE ALL ON SEQUENCE orders.{table}_id_seq FROM {RUNTIME_ROLE}")
        op.execute(f"REVOKE ALL ON orders.{table} FROM {RUNTIME_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA orders FROM {RUNTIME_ROLE}")
