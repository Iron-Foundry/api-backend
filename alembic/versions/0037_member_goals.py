"""add member_goals table

Revision ID: 0037
Revises: 0036
Create Date: 2026-06-26
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "member_goals",
        sa.Column("id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column("discord_user_id", sa.BigInteger(), nullable=False),
        sa.Column("rsn", sa.Text(), nullable=False),
        sa.Column("goals", JSONB(), nullable=False, server_default="[]"),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("discord_user_id", "rsn", name="uq_member_goals_user_rsn"),
    )


def downgrade() -> None:
    op.drop_table("member_goals")
