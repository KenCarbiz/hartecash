"""lead first_responded_at column

Revision ID: 0036
Revises: 0035
Create Date: 2026-05-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0036"
down_revision: Union[str, None] = "0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column(
            "first_responded_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_leads_first_responded_at",
        "leads",
        ["first_responded_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_leads_first_responded_at", table_name="leads")
    op.drop_column("leads", "first_responded_at")
