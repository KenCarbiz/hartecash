"""extension_install_codes table

Revision ID: 0022
Revises: 0021
Create Date: 2026-05-05

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "extension_install_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dealer_id", sa.String(length=64), nullable=False),
        sa.Column("issued_by_user_id", sa.Integer(), nullable=True),
        sa.Column("code_hash", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_install_codes_hash",
        "extension_install_codes",
        ["code_hash"],
        unique=True,
    )
    op.create_index(
        "ix_extension_install_codes_dealer_id",
        "extension_install_codes",
        ["dealer_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_extension_install_codes_dealer_id",
        table_name="extension_install_codes",
    )
    op.drop_index("ix_install_codes_hash", table_name="extension_install_codes")
    op.drop_table("extension_install_codes")
