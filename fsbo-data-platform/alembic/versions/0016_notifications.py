"""notification preferences + delivery dedup

Revision ID: 0016
Revises: 0015
Create Date: 2026-04-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "alerts_enabled", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "alert_min_score", sa.Integer(), nullable=False, server_default="80"
        ),
    )

    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("listing_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "user_id", "listing_id", "kind", name="uq_notif_user_listing_kind"
        ),
    )
    op.create_index(
        "ix_notification_deliveries_user_id",
        "notification_deliveries",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_table("notification_deliveries")
    op.drop_column("users", "alert_min_score")
    op.drop_column("users", "alerts_enabled")
