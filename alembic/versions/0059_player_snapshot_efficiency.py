"""carry WOM efficiency values on player snapshots

Revision ID: 0059
Revises: 0058
Create Date: 2026-07-31
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("player_snapshots", sa.Column("ehp", sa.Float(), nullable=True))
    op.add_column("player_snapshots", sa.Column("ehb", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("player_snapshots", "ehb")
    op.drop_column("player_snapshots", "ehp")
