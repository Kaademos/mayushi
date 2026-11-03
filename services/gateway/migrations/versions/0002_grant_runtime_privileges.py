"""grant runtime privileges to gateway_svc

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-03 10:30:00

The gateway only reads tenants. Later migrations grant each new table explicitly.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNTIME_ROLE = "gateway_svc"


def upgrade() -> None:
    op.execute(f"GRANT USAGE ON SCHEMA app TO {RUNTIME_ROLE}")
    op.execute(f"GRANT SELECT ON app.tenants TO {RUNTIME_ROLE}")


def downgrade() -> None:
    op.execute(f"REVOKE ALL ON app.tenants FROM {RUNTIME_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA app FROM {RUNTIME_ROLE}")
