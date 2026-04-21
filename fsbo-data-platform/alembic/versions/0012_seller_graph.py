"""seller identity graph

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "seller_identities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("value", sa.String(256), nullable=False),
        sa.Column("listing_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("kind", "value", name="uq_seller_identity_kind_value"),
    )
    op.create_index("ix_seller_identities_kind", "seller_identities", ["kind"])
    op.create_index("ix_seller_identities_value", "seller_identities", ["value"])

    op.create_table(
        "seller_identity_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("listing_id", sa.Integer(), nullable=False),
        sa.Column("identity_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "listing_id", "identity_id", name="uq_seller_identity_link"
        ),
    )
    op.create_index(
        "ix_seller_identity_links_listing", "seller_identity_links", ["listing_id"]
    )
    op.create_index(
        "ix_seller_identity_links_identity", "seller_identity_links", ["identity_id"]
    )


def downgrade() -> None:
    op.drop_table("seller_identity_links")
    op.drop_table("seller_identities")
