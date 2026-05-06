"""history_report cache columns on listings

Revision ID: 0029
Revises: 0028
Create Date: 2026-05-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "listings",
        sa.Column(
            "history_report",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "listings",
        sa.Column(
            "history_report_fetched_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("listings", "history_report_fetched_at")
    op.drop_column("listings", "history_report")
