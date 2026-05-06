"""composite index for the default /listings feed query

Revision ID: 0023
Revises: 0022
Create Date: 2026-05-05

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_listings_default_feed",
        "listings",
        ["classification", "auto_hidden", "posted_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_listings_default_feed", table_name="listings")
