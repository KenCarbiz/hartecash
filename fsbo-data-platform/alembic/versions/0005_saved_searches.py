"""saved searches

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "saved_searches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dealer_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("query", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("alerts_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("dealer_id", "name", name="uq_search_dealer_name"),
    )
    op.create_index("ix_saved_searches_dealer_id", "saved_searches", ["dealer_id"])


def downgrade() -> None:
    op.drop_table("saved_searches")
