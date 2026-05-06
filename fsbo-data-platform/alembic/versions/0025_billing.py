"""dealer.stripe_customer_id + subscriptions table

Revision ID: 0025
Revises: 0024
Create Date: 2026-05-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dealers",
        sa.Column("stripe_customer_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_dealers_stripe_customer_id",
        "dealers",
        ["stripe_customer_id"],
        unique=True,
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dealer_id", sa.String(length=64), nullable=False),
        sa.Column(
            "stripe_subscription_id", sa.String(length=64), nullable=False
        ),
        sa.Column("stripe_customer_id", sa.String(length=64), nullable=False),
        sa.Column("plan", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "current_period_end", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "cancel_at_period_end",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
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
        sa.UniqueConstraint(
            "stripe_subscription_id", name="uq_sub_stripe_id"
        ),
    )
    op.create_index(
        "ix_subscriptions_dealer_id", "subscriptions", ["dealer_id"]
    )
    op.create_index(
        "ix_subscriptions_dealer_active",
        "subscriptions",
        ["dealer_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_subscriptions_dealer_active", table_name="subscriptions"
    )
    op.drop_index("ix_subscriptions_dealer_id", table_name="subscriptions")
    op.drop_table("subscriptions")
    op.drop_index("ix_dealers_stripe_customer_id", table_name="dealers")
    op.drop_column("dealers", "stripe_customer_id")
