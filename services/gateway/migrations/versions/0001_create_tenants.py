"""create tenants

Revision ID: 0001
Revises:
Create Date: 2026-11-02 22:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    tenants = op.create_table(
        "tenants",
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("slug", name=op.f("pk_tenants")),
        schema="app",
    )
    op.bulk_insert(
        tenants,
        [
            {
                "slug": "northwind-retail",
                "display_name": "Northwind Parcel Co. (Retail)",
                "is_active": True,
            },
            {
                "slug": "northwind-b2b",
                "display_name": "Northwind Parcel Co. (Business)",
                "is_active": True,
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("tenants", schema="app")
