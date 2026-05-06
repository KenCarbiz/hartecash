"""lead unread-inbound tracking columns

Revision ID: 0037
Revises: 0036
Create Date: 2026-05-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0037"
down_revision: Union[str, None] = "0036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "leads",
        sa.Column(
            "last_seen_inbound_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    op.create_index(
        "ix_leads_last_inbound_at", "leads", ["last_inbound_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_leads_last_inbound_at", table_name="leads")
    op.drop_column("leads", "last_seen_inbound_at")
    op.drop_column("leads", "last_inbound_at")
