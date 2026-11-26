"""staff-set kill rates for osrsclans drop sources

Revision ID: 0064
Revises: 0063
Create Date: 2026-11-26
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_kill_rates",
        sa.Column("source", sa.Text(), primary_key=True),
        sa.Column("kills_per_hour", sa.Float(), nullable=False),
        sa.Column("set_by", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint("kills_per_hour > 0", name="ck_source_kill_rate_positive"),
    )


def downgrade() -> None:
    op.drop_table("source_kill_rates")
