"""frenzy captain drafts

Revision ID: 0069
Revises: 0068
Create Date: 2026-11-26
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0069"
down_revision = "0068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "frenzy_signups",
        sa.Column(
            "wants_captain", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "frenzy_signups",
        sa.Column(
            "team_id",
            sa.BigInteger(),
            sa.ForeignKey("frenzy_teams.id", ondelete="SET NULL"),
        ),
    )
    op.add_column("frenzy_signups", sa.Column("pick_number", sa.Integer()))
    op.add_column("frenzy_signups", sa.Column("pick_kind", sa.Text()))
    op.create_index("ix_frenzy_signups_team_id", "frenzy_signups", ["team_id"])
    op.create_table(
        "frenzy_drafts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "event_id",
            sa.BigInteger(),
            sa.ForeignKey("frenzy_events.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("top_picks", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("captain_ids", JSONB(), nullable=False, server_default="[]"),
        sa.Column("team_ids", JSONB(), nullable=False, server_default="[]"),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("next_pick", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("frenzy_drafts")
    op.drop_index("ix_frenzy_signups_team_id", table_name="frenzy_signups")
    op.drop_column("frenzy_signups", "pick_kind")
    op.drop_column("frenzy_signups", "pick_number")
    op.drop_column("frenzy_signups", "team_id")
    op.drop_column("frenzy_signups", "wants_captain")
