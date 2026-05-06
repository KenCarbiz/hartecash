"""dealer_id on webhook_subscriptions

Revision ID: 0032
Revises: 0031
Create Date: 2026-05-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: Union[str, None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "webhook_subscriptions",
        sa.Column(
            "dealer_id",
            sa.String(length=64),
            nullable=False,
            server_default="",
        ),
    )
    op.create_index(
        "ix_webhook_subs_dealer_id",
        "webhook_subscriptions",
        ["dealer_id"],
    )
    op.create_index(
        "ix_webhook_subs_dealer_event",
        "webhook_subscriptions",
        ["dealer_id", "event", "active"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_webhook_subs_dealer_event", table_name="webhook_subscriptions"
    )
    op.drop_index(
        "ix_webhook_subs_dealer_id", table_name="webhook_subscriptions"
    )
    op.drop_column("webhook_subscriptions", "dealer_id")
