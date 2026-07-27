"""add activities column to player_snapshots

Revision ID: 0036
Revises: 0035
Create Date: 2026-06-26
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "player_snapshots",
        sa.Column("activities", JSONB(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("player_snapshots", "activities")
