"""crm leads and interactions

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "leads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dealer_id", sa.String(64), nullable=False),
        sa.Column("listing_id", sa.Integer(), nullable=False),
        sa.Column("assigned_to", sa.String(128)),
        sa.Column("status", sa.String(32), nullable=False, server_default="new"),
        sa.Column("offered_price", sa.Float()),
        sa.Column("notes", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("dealer_id", "listing_id", name="uq_lead_dealer_listing"),
    )
    op.create_index("ix_leads_dealer_id", "leads", ["dealer_id"])
    op.create_index("ix_leads_listing_id", "leads", ["listing_id"])
    op.create_index("ix_leads_status", "leads", ["status"])

    op.create_table(
        "interactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lead_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("direction", sa.String(16)),
        sa.Column("actor", sa.String(128)),
        sa.Column("body", sa.Text()),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("meta", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_interactions_lead_created", "interactions", ["lead_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_table("interactions")
    op.drop_table("leads")
