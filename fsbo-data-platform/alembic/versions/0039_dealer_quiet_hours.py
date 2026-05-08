"""dealer quiet-hours override columns

Revision ID: 0039
Revises: 0038
Create Date: 2026-05-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0039"
down_revision: Union[str, None] = "0038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dealers",
        sa.Column("quiet_hours_start", sa.String(length=5), nullable=True),
    )
    op.add_column(
        "dealers",
        sa.Column("quiet_hours_end", sa.String(length=5), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dealers", "quiet_hours_end")
    op.drop_column("dealers", "quiet_hours_start")
