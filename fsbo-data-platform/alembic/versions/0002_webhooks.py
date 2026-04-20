"""webhooks

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "webhook_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("secret", sa.String(128), nullable=False),
        sa.Column("event", sa.String(64), nullable=False, server_default="listing.created"),
        sa.Column("filters", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("listing_id", sa.Integer()),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_status_code", sa.Integer()),
        sa.Column("last_error", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_webhook_deliveries_subscription_id", "webhook_deliveries", ["subscription_id"]
    )
    op.create_index(
        "ix_webhook_deliveries_status",
        "webhook_deliveries",
        ["status", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_table("webhook_deliveries")
    op.drop_table("webhook_subscriptions")
