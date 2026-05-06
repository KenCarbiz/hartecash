"""SMS opt-out registry + consent ledger (TCPA compliance)

Revision ID: 0026
Revises: 0025
Create Date: 2026-05-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sms_opt_outs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dealer_id", sa.String(length=64), nullable=False),
        sa.Column("phone", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("note", sa.String(length=256), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "dealer_id", "phone", name="uq_optout_dealer_phone"
        ),
    )
    op.create_index(
        "ix_sms_opt_outs_dealer_id", "sms_opt_outs", ["dealer_id"]
    )
    op.create_index("ix_sms_opt_outs_phone", "sms_opt_outs", ["phone"])

    op.create_table(
        "sms_consents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dealer_id", sa.String(length=64), nullable=False),
        sa.Column("phone", sa.String(length=16), nullable=False),
        sa.Column("consent_text", sa.Text(), nullable=False),
        sa.Column("captured_via", sa.String(length=32), nullable=False),
        sa.Column("captured_by_user", sa.String(length=255), nullable=True),
        sa.Column(
            "revoked_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "dealer_id", "phone", name="uq_consent_dealer_phone"
        ),
    )
    op.create_index(
        "ix_sms_consents_dealer_id", "sms_consents", ["dealer_id"]
    )
    op.create_index("ix_sms_consents_phone", "sms_consents", ["phone"])


def downgrade() -> None:
    op.drop_index("ix_sms_consents_phone", table_name="sms_consents")
    op.drop_index("ix_sms_consents_dealer_id", table_name="sms_consents")
    op.drop_table("sms_consents")
    op.drop_index("ix_sms_opt_outs_phone", table_name="sms_opt_outs")
    op.drop_index("ix_sms_opt_outs_dealer_id", table_name="sms_opt_outs")
    op.drop_table("sms_opt_outs")
