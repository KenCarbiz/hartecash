"""dealer_groups table + Dealer.group_id

Revision ID: 0033
Revises: 0032
Create Date: 2026-05-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: Union[str, None] = "0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dealer_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column(
            "owner_dealer_id", sa.String(length=64), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("slug", name="uq_dealer_groups_slug"),
    )
    op.create_index(
        "ix_dealer_groups_slug", "dealer_groups", ["slug"], unique=True
    )
    op.create_index(
        "ix_dealer_groups_owner_dealer_id",
        "dealer_groups",
        ["owner_dealer_id"],
    )

    op.add_column(
        "dealers", sa.Column("group_id", sa.Integer(), nullable=True)
    )
    op.create_index("ix_dealers_group_id", "dealers", ["group_id"])


def downgrade() -> None:
    op.drop_index("ix_dealers_group_id", table_name="dealers")
    op.drop_column("dealers", "group_id")
    op.drop_index(
        "ix_dealer_groups_owner_dealer_id", table_name="dealer_groups"
    )
    op.drop_index("ix_dealer_groups_slug", table_name="dealer_groups")
    op.drop_table("dealer_groups")
