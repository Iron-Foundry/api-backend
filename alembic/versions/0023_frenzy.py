"""add frenzy templates, events, and teams tables

Revision ID: 0023
Revises: 0022
Create Date: 2026-06-01
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "frenzy_templates",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tiers", JSONB(), nullable=False, server_default="{}"),
        sa.Column("activities", JSONB(), nullable=False, server_default="[]"),
        sa.Column("milestones", JSONB(), nullable=False, server_default="{}"),
        sa.Column("multipliers", JSONB(), nullable=False, server_default="[]"),
        sa.Column("version_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )

    op.create_table(
        "frenzy_template_versions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "template_id",
            sa.BigInteger(),
            sa.ForeignKey("frenzy_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("tiers", JSONB(), nullable=False),
        sa.Column("activities", JSONB(), nullable=False),
        sa.Column("milestones", JSONB(), nullable=False),
        sa.Column("multipliers", JSONB(), nullable=False),
        sa.Column("edited_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_frenzy_template_versions_lookup",
        "frenzy_template_versions",
        ["template_id", "version_number"],
    )

    op.create_table(
        "frenzy_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "template_id",
            sa.BigInteger(),
            sa.ForeignKey("frenzy_templates.id"),
            nullable=False,
        ),
        sa.Column("wom_comp_id", sa.Integer(), nullable=True),
        sa.Column("leaderboard_metrics", JSONB(), nullable=False, server_default="[]"),
        sa.Column("starts_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("ends_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )

    op.create_table(
        "frenzy_teams",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "event_id",
            sa.BigInteger(),
            sa.ForeignKey("frenzy_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("icon_url", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("item_progress", JSONB(), nullable=False, server_default="{}"),
        sa.Column("activity_progress", JSONB(), nullable=False, server_default="{}"),
        sa.Column("milestone_progress", JSONB(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.UniqueConstraint("event_id", "slug", name="uq_frenzy_team_slug"),
    )


def downgrade() -> None:
    op.drop_table("frenzy_teams")
    op.drop_table("frenzy_events")
    op.drop_index("ix_frenzy_template_versions_lookup", "frenzy_template_versions")
    op.drop_table("frenzy_template_versions")
    op.drop_table("frenzy_templates")
