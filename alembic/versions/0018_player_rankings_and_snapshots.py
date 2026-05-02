"""add player_rankings and player_snapshots tables

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-02
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "player_rankings",
        sa.Column("rsn", sa.Text(), nullable=False),
        sa.Column("rank", sa.Text(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("boss_points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skill_points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("discord_user_id", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("rsn"),
    )
    op.create_table(
        "player_snapshots",
        sa.Column("rsn", sa.Text(), nullable=False),
        sa.Column("skills", JSONB(), nullable=False, server_default="{}"),
        sa.Column("bosses", JSONB(), nullable=False, server_default="{}"),
        sa.Column("fetched_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("rsn"),
    )


def downgrade() -> None:
    op.drop_table("player_snapshots")
    op.drop_table("player_rankings")
