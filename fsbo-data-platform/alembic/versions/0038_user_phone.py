"""user phone column (default rep phone for click-to-call bridge)

Revision ID: 0038
Revises: 0037
Create Date: 2026-05-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0038"
down_revision: Union[str, None] = "0037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("phone", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "phone")
