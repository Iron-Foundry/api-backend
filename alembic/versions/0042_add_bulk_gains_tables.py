"""add bulk gains tables

Revision ID: 0042
Revises: 0041
Create Date: 2026-07-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bulk_gains_batches",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("period", sa.Text(), nullable=True),
        sa.Column("start_date", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("end_date", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("captured_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_bulk_gains_batches_captured_at", "bulk_gains_batches", ["captured_at"]
    )
    op.create_table(
        "player_bulk_gains",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("rsn", sa.Text(), nullable=False),
        sa.Column("gains_start", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("gains_end", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("skills", JSONB(), nullable=False, server_default="{}"),
        sa.Column("bosses", JSONB(), nullable=False, server_default="{}"),
        sa.Column("activities", JSONB(), nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(
            ["batch_id"], ["bulk_gains_batches.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_player_bulk_gains_batch_id", "player_bulk_gains", ["batch_id"])
    op.create_index(
        "ix_player_bulk_gains_rsn_range",
        "player_bulk_gains",
        ["rsn", "gains_start", "gains_end"],
    )


def downgrade() -> None:
    op.drop_index("ix_player_bulk_gains_rsn_range", table_name="player_bulk_gains")
    op.drop_index("ix_player_bulk_gains_batch_id", table_name="player_bulk_gains")
    op.drop_table("player_bulk_gains")
    op.drop_index("ix_bulk_gains_batches_captured_at", table_name="bulk_gains_batches")
    op.drop_table("bulk_gains_batches")
