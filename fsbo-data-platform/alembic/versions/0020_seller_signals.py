"""seller_profile_url + seller_joined_year on listings

Revision ID: 0020
Revises: 0019
Create Date: 2026-05-05

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "listings", sa.Column("seller_profile_url", sa.Text(), nullable=True)
    )
    op.add_column(
        "listings", sa.Column("seller_joined_year", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("listings", "seller_joined_year")
    op.drop_column("listings", "seller_profile_url")
