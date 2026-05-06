"""sold_at + sold_signal on listings

Revision ID: 0027
Revises: 0026
Create Date: 2026-05-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "listings",
        sa.Column("sold_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "listings", sa.Column("sold_signal", sa.String(length=256), nullable=True)
    )
    op.create_index("ix_listings_sold_at", "listings", ["sold_at"])


def downgrade() -> None:
    op.drop_index("ix_listings_sold_at", table_name="listings")
    op.drop_column("listings", "sold_signal")
    op.drop_column("listings", "sold_at")
