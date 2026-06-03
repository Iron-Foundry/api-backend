"""add frenzy_submissions table and trusted_sources to frenzy_events

Revision ID: 0025
Revises: 0024
Create Date: 2026-06-02
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "frenzy_events",
        sa.Column("trusted_sources", JSONB, nullable=False, server_default="[]"),
    )

    op.create_table(
        "frenzy_submissions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "event_id",
            sa.BigInteger(),
            sa.ForeignKey("frenzy_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "team_id",
            sa.BigInteger(),
            sa.ForeignKey("frenzy_teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("discord_user_id", sa.BigInteger(), nullable=False),
        sa.Column("player_rsn", sa.Text(), nullable=False),
        # trackscape | discord_ocr | discord_manual | web
        sa.Column("source", sa.Text(), nullable=False),
        # item | activity | milestone
        sa.Column("submission_type", sa.Text(), nullable=False),
        # item:      { tier, source_name, item_name, quantity }
        # activity:  { name, value }
        # milestone: { name, value }
        sa.Column("payload", JSONB(), nullable=False, server_default="{}"),
        # pending | approved | rejected
        sa.Column("status", sa.Text(), nullable=False, server_default="'pending'"),
        sa.Column("auto_approved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("reviewed_by", sa.BigInteger(), nullable=True),
        sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_frenzy_submissions_team_status",
        "frenzy_submissions",
        ["team_id", "status"],
    )
    op.create_index(
        "ix_frenzy_submissions_event_status",
        "frenzy_submissions",
        ["event_id", "status", "submitted_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_frenzy_submissions_event_status", "frenzy_submissions")
    op.drop_index("ix_frenzy_submissions_team_status", "frenzy_submissions")
    op.drop_table("frenzy_submissions")
    op.drop_column("frenzy_events", "trusted_sources")
