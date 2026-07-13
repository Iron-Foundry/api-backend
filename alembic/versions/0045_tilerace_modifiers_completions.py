"""add tilerace requirement, dice, pending effects and completions

Revision ID: 0045
Revises: 0044
Create Date: 2026-07-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tile_repository_tiles",
        sa.Column("requirement", JSONB(), nullable=True),
    )
    op.add_column(
        "tilerace_events",
        sa.Column("dice_count", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "tilerace_events",
        sa.Column("dice_sides", sa.Integer(), nullable=False, server_default="6"),
    )
    op.add_column(
        "tilerace_teams",
        sa.Column("pending_effects", JSONB(), nullable=False, server_default="{}"),
    )
    op.create_table(
        "tilerace_tile_completions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("team_id", sa.BigInteger(), nullable=False),
        sa.Column("path_position", sa.Integer(), nullable=False),
        sa.Column("completed_by", sa.BigInteger(), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["event_id"], ["tilerace_events.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["team_id"], ["tilerace_teams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "path_position", name="uq_tilerace_completion"),
    )


def downgrade() -> None:
    op.drop_table("tilerace_tile_completions")
    op.drop_column("tilerace_teams", "pending_effects")
    op.drop_column("tilerace_events", "dice_sides")
    op.drop_column("tilerace_events", "dice_count")
    op.drop_column("tile_repository_tiles", "requirement")
