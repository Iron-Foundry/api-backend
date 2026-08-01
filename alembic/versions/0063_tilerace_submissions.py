"""tile race submissions, claim status and rollback anchor

Revision ID: 0063
Revises: 0062
Create Date: 2026-08-01
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tilerace_events",
        sa.Column("discord_submissions_channel_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "tilerace_teams",
        sa.Column(
            "furthest_position",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "tilerace_tile_completions",
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'approved'"),
        ),
    )
    op.create_table(
        "tilerace_submissions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("team_id", sa.BigInteger(), nullable=False),
        sa.Column("path_position", sa.Integer(), nullable=False),
        sa.Column("tile_id", sa.BigInteger(), nullable=True),
        sa.Column("leaf_key", sa.Text(), nullable=False),
        sa.Column(
            "leaf_label", sa.Text(), nullable=False, server_default=sa.text("''")
        ),
        sa.Column("discord_user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "player_rsn", sa.Text(), nullable=False, server_default=sa.text("''")
        ),
        sa.Column(
            "proof_urls",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("discord_thread_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "status", sa.Text(), nullable=False, server_default=sa.text("'pending'")
        ),
        sa.Column("reviewed_by", sa.BigInteger(), nullable=True),
        sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["event_id"], ["tilerace_events.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["team_id"], ["tilerace_teams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tilerace_submissions_event_status",
        "tilerace_submissions",
        ["event_id", "status", "submitted_at"],
    )
    op.create_index(
        "ix_tilerace_submissions_team_position",
        "tilerace_submissions",
        ["team_id", "path_position"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tilerace_submissions_team_position", table_name="tilerace_submissions"
    )
    op.drop_index(
        "ix_tilerace_submissions_event_status", table_name="tilerace_submissions"
    )
    op.drop_table("tilerace_submissions")
    op.drop_column("tilerace_tile_completions", "status")
    op.drop_column("tilerace_teams", "furthest_position")
    op.drop_column("tilerace_events", "discord_submissions_channel_id")
