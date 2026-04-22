"""license plate + color on listings

Revision ID: 0017
Revises: 0016
Create Date: 2026-04-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("license_plate", sa.String(16)))
    op.add_column("listings", sa.Column("license_plate_state", sa.String(4)))
    op.add_column("listings", sa.Column("color", sa.String(32)))
    op.create_index(
        "ix_listings_license_plate", "listings", ["license_plate"]
    )


def downgrade() -> None:
    op.drop_index("ix_listings_license_plate", table_name="listings")
    op.drop_column("listings", "color")
    op.drop_column("listings", "license_plate_state")
    op.drop_column("listings", "license_plate")
