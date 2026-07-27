"""add wom_clan_ranks table

Revision ID: 0040
Revises: 0039
Create Date: 2026-06-29
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wom_clan_ranks",
        sa.Column("rsn", sa.Text(), nullable=False),
        sa.Column("clan_rank", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("rsn"),
    )


def downgrade() -> None:
    op.drop_table("wom_clan_ranks")
