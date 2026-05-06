"""dealer routing config columns

Revision ID: 0031
Revises: 0030
Create Date: 2026-05-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dealers",
        sa.Column(
            "routing_mode",
            sa.String(length=16),
            nullable=False,
            server_default="manual",
        ),
    )
    op.add_column(
        "dealers",
        sa.Column(
            "routing_pool",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("dealers", "routing_pool")
    op.drop_column("dealers", "routing_mode")
