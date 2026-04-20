"""auto_hidden flag + reason

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "listings",
        sa.Column("auto_hidden", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("listings", sa.Column("auto_hide_reason", sa.String(64)))
    op.create_index("ix_listings_auto_hidden", "listings", ["auto_hidden"])


def downgrade() -> None:
    op.drop_index("ix_listings_auto_hidden", table_name="listings")
    op.drop_column("listings", "auto_hide_reason")
    op.drop_column("listings", "auto_hidden")
