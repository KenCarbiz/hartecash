"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "listings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(256), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.Column("year", sa.Integer()),
        sa.Column("make", sa.String(64)),
        sa.Column("model", sa.String(128)),
        sa.Column("trim", sa.String(128)),
        sa.Column("mileage", sa.Integer()),
        sa.Column("price", sa.Float()),
        sa.Column("vin", sa.String(17)),
        sa.Column("city", sa.String(128)),
        sa.Column("state", sa.String(8)),
        sa.Column("zip_code", sa.String(16)),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("seller_name", sa.String(256)),
        sa.Column("seller_phone", sa.String(32)),
        sa.Column("classification", sa.String(32), nullable=False, server_default="unclassified"),
        sa.Column("classification_confidence", sa.Float()),
        sa.Column("classification_reason", sa.Text()),
        sa.Column("raw", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("images", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("posted_at", sa.DateTime(timezone=True)),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("dedup_key", sa.String(128)),
        sa.UniqueConstraint("source", "external_id", name="uq_source_external_id"),
    )
    op.create_index("ix_listings_geo", "listings", ["zip_code"])
    op.create_index("ix_listings_vehicle", "listings", ["make", "model", "year"])
    op.create_index("ix_listings_classification", "listings", ["classification"])
    op.create_index("ix_listings_posted_at", "listings", ["posted_at"])
    op.create_index("ix_listings_vin", "listings", ["vin"])
    op.create_index("ix_listings_seller_phone", "listings", ["seller_phone"])
    op.create_index("ix_listings_dedup_key", "listings", ["dedup_key"])

    op.create_table(
        "scrape_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("fetched_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inserted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text()),
    )
    op.create_index("ix_scrape_runs_source", "scrape_runs", ["source"])


def downgrade() -> None:
    op.drop_table("scrape_runs")
    op.drop_table("listings")
