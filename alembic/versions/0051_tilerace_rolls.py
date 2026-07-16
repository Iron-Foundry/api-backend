"""add tilerace rolls log

Revision ID: 0051
Revises: 0050
Create Date: 2026-07-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tilerace_rolls",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("team_id", sa.BigInteger(), nullable=False),
        sa.Column("dice", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("roll", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("new_position", sa.Integer(), nullable=False),
        sa.Column("rolled_by", sa.BigInteger(), nullable=False),
        sa.Column("rolled_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["event_id"], ["tilerace_events.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["team_id"], ["tilerace_teams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tilerace_rolls_event_rolled_at",
        "tilerace_rolls",
        ["event_id", "rolled_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_tilerace_rolls_event_rolled_at", table_name="tilerace_rolls")
    op.drop_table("tilerace_rolls")
