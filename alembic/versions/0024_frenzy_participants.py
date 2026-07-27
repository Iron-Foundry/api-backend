"""add participants column to frenzy_teams

Revision ID: 0024
Revises: 0023
Create Date: 2026-06-01
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "frenzy_teams",
        sa.Column("participants", JSONB, nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("frenzy_teams", "participants")
