"""add tilerace finished state

Revision ID: 0047
Revises: 0046
Create Date: 2026-07-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tilerace_events",
        sa.Column("is_finished", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "tilerace_events",
        sa.Column("winner_team_id", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tilerace_events", "winner_team_id")
    op.drop_column("tilerace_events", "is_finished")
