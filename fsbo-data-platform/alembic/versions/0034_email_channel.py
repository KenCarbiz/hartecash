"""seller_email + Message channel/email columns

Revision ID: 0034
Revises: 0033
Create Date: 2026-05-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0034"
down_revision: Union[str, None] = "0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Listings: capture seller email (from extension or manual)
    op.add_column(
        "listings",
        sa.Column("seller_email", sa.String(length=256), nullable=True),
    )
    op.create_index("ix_listings_seller_email", "listings", ["seller_email"])

    # Messages: channel + email leg fields
    op.add_column(
        "messages",
        sa.Column(
            "channel",
            sa.String(length=16),
            nullable=False,
            server_default="sms",
        ),
    )
    op.add_column(
        "messages",
        sa.Column("from_email", sa.String(length=256), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("to_email", sa.String(length=256), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("subject", sa.String(length=256), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("messages", "subject")
    op.drop_column("messages", "to_email")
    op.drop_column("messages", "from_email")
    op.drop_column("messages", "channel")
    op.drop_index("ix_listings_seller_email", table_name="listings")
    op.drop_column("listings", "seller_email")
