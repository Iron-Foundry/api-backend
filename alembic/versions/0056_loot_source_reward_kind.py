"""add reward_kind to loot_sources

Revision ID: 0056
Revises: 0055
Create Date: 2026-07-26
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("loot_sources", sa.Column("reward_kind", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("loot_sources", "reward_kind")
