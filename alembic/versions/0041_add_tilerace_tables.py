"""add tilerace tables

Revision ID: 0041
Revises: 0040
Create Date: 2026-07-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tile_repository_tiles",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("icon_url", sa.Text(), nullable=True),
        sa.Column("icon_source", sa.Text(), nullable=False, server_default="wiki"),
        sa.Column("items", JSONB(), nullable=False, server_default="[]"),
        sa.Column("tags", JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "tilerace_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("fog_of_war", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("grid_cols", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("grid_rows", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("background_url", sa.Text(), nullable=True),
        sa.Column("cells", JSONB(), nullable=False, server_default="[]"),
        sa.Column("starts_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("ends_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "tilerace_teams",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("icon_type", sa.Text(), nullable=False, server_default="item"),
        sa.Column("icon_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("color", sa.Text(), nullable=False, server_default="#888888"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("members", JSONB(), nullable=False, server_default="[]"),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["event_id"], ["tilerace_events.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "slug", name="uq_tilerace_team_slug"),
    )
    op.create_table(
        "tilerace_signups",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("discord_user_id", sa.BigInteger(), nullable=False),
        sa.Column("rsn", sa.Text(), nullable=False),
        sa.Column("ranking_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("signed_up_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["event_id"], ["tilerace_events.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "discord_user_id", name="uq_tilerace_signup"),
    )


def downgrade() -> None:
    op.drop_table("tilerace_signups")
    op.drop_table("tilerace_teams")
    op.drop_table("tilerace_events")
    op.drop_table("tile_repository_tiles")
