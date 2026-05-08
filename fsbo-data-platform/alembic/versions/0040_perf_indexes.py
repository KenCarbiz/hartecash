"""composite indexes for hot leaderboard + routing queries

Revision ID: 0040
Revises: 0039
Create Date: 2026-05-08

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0040"
down_revision: Union[str, None] = "0039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_leads_dealer_assigned",
        "leads",
        ["dealer_id", "assigned_to"],
    )
    op.create_index(
        "ix_messages_dealer_dir_created",
        "messages",
        ["dealer_id", "direction", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_messages_dealer_dir_created", table_name="messages")
    op.drop_index("ix_leads_dealer_assigned", table_name="leads")
