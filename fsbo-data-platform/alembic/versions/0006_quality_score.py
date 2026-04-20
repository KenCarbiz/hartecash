"""quality score + dealer likelihood columns

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("dealer_likelihood", sa.Float()))
    op.add_column("listings", sa.Column("scam_score", sa.Float()))
    op.add_column("listings", sa.Column("lead_quality_score", sa.Integer()))
    op.add_column(
        "listings",
        sa.Column("quality_breakdown", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_listings_lead_quality_score", "listings", ["lead_quality_score"])


def downgrade() -> None:
    op.drop_index("ix_listings_lead_quality_score", table_name="listings")
    op.drop_column("listings", "quality_breakdown")
    op.drop_column("listings", "lead_quality_score")
    op.drop_column("listings", "scam_score")
    op.drop_column("listings", "dealer_likelihood")
