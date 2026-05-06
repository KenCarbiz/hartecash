"""voice_calls table + lead.seller_intake column

Revision ID: 0028
Revises: 0027
Create Date: 2026-05-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column(
            "seller_intake",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
    )

    op.create_table(
        "voice_calls",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lead_id", sa.Integer(), nullable=False),
        sa.Column("dealer_id", sa.String(length=64), nullable=False),
        sa.Column(
            "twilio_call_sid", sa.String(length=64), nullable=True
        ),
        sa.Column(
            "direction",
            sa.String(length=16),
            nullable=False,
            server_default="outbound",
        ),
        sa.Column("to_number", sa.String(length=32), nullable=False),
        sa.Column("from_number", sa.String(length=32), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="queued",
        ),
        sa.Column(
            "turns", sa.JSON(), nullable=False, server_default="[]"
        ),
        sa.Column(
            "intake", sa.JSON(), nullable=False, server_default="{}"
        ),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
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
            "twilio_call_sid", name="uq_voice_call_sid"
        ),
    )
    op.create_index(
        "ix_voice_calls_dealer_id", "voice_calls", ["dealer_id"]
    )
    op.create_index(
        "ix_voice_calls_twilio_call_sid",
        "voice_calls",
        ["twilio_call_sid"],
    )
    op.create_index(
        "ix_voice_calls_lead_created",
        "voice_calls",
        ["lead_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_voice_calls_lead_created", table_name="voice_calls")
    op.drop_index(
        "ix_voice_calls_twilio_call_sid", table_name="voice_calls"
    )
    op.drop_index("ix_voice_calls_dealer_id", table_name="voice_calls")
    op.drop_table("voice_calls")
    op.drop_column("leads", "seller_intake")
