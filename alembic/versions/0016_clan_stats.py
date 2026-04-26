"""add clan_stats table for hourly WOM snapshot

Revision ID: 0016
Revises: 0015
Create Date: 2026-04-26
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clan_stats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("member_count", sa.Integer(), nullable=True),
        sa.Column("total_xp", sa.BigInteger(), nullable=True),
        sa.Column("total_ehb", sa.Integer(), nullable=True),
        sa.Column("cox_kc", sa.Integer(), nullable=True),
        sa.Column("tob_kc", sa.Integer(), nullable=True),
        sa.Column("toa_kc", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("clan_stats")
