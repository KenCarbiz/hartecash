"""messages table

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dealer_id", sa.String(64), nullable=False),
        sa.Column("lead_id", sa.Integer()),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("from_number", sa.String(32)),
        sa.Column("to_number", sa.String(32)),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("error_code", sa.String(32)),
        sa.Column("twilio_sid", sa.String(64)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_messages_dealer_id", "messages", ["dealer_id"])
    op.create_index("ix_messages_lead", "messages", ["lead_id"])
    op.create_index("ix_messages_twilio_sid", "messages", ["twilio_sid"])


def downgrade() -> None:
    op.drop_table("messages")
