"""offers table — seller-facing firm cash offers with public tokens

Revision ID: 0030
Revises: 0029
Create Date: 2026-05-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "offers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_token", sa.String(length=64), nullable=False),
        sa.Column("dealer_id", sa.String(length=64), nullable=False),
        sa.Column("lead_id", sa.Integer(), nullable=False),
        sa.Column("listing_id", sa.Integer(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column(
            "breakdown",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "expires_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "seller_response_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "seller_response_note", sa.Text(), nullable=True
        ),
        sa.Column(
            "seller_viewed_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("public_token", name="uq_offers_public_token"),
    )
    op.create_index(
        "ix_offers_public_token", "offers", ["public_token"], unique=True
    )
    op.create_index("ix_offers_dealer_id", "offers", ["dealer_id"])
    op.create_index("ix_offers_status", "offers", ["status"])
    op.create_index(
        "ix_offers_lead_created", "offers", ["lead_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_offers_lead_created", table_name="offers")
    op.drop_index("ix_offers_status", table_name="offers")
    op.drop_index("ix_offers_dealer_id", table_name="offers")
    op.drop_index("ix_offers_public_token", table_name="offers")
    op.drop_table("offers")
