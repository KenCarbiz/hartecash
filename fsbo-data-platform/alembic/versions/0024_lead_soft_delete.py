"""soft-delete columns on leads

Revision ID: 0024
Revises: 0023
Create Date: 2026-05-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "leads", sa.Column("deleted_by", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "leads",
        sa.Column("delete_reason", sa.String(length=256), nullable=True),
    )
    op.create_index("ix_leads_deleted_at", "leads", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_leads_deleted_at", table_name="leads")
    op.drop_column("leads", "delete_reason")
    op.drop_column("leads", "deleted_by")
    op.drop_column("leads", "deleted_at")
