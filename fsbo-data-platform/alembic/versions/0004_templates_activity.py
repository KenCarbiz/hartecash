"""message templates and daily activity

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "message_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dealer_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("category", sa.String(32), nullable=False, server_default="outreach"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("dealer_id", "name", name="uq_template_dealer_name"),
    )
    op.create_index("ix_message_templates_dealer_id", "message_templates", ["dealer_id"])

    op.create_table(
        "daily_activity",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dealer_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("date", sa.String(10), nullable=False),
        sa.Column("messages_sent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("calls_made", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("offers_made", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("appointments", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("purchases", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("goal_messages", sa.Integer(), nullable=False, server_default="60"),
        sa.UniqueConstraint(
            "dealer_id", "user_id", "date", name="uq_activity_user_date"
        ),
    )
    op.create_index("ix_daily_activity_dealer_id", "daily_activity", ["dealer_id"])


def downgrade() -> None:
    op.drop_table("daily_activity")
    op.drop_table("message_templates")
