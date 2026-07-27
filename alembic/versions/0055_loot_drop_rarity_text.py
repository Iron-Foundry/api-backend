"""add qualitative rarity_text to loot_drops

Revision ID: 0055
Revises: 0054
Create Date: 2026-07-26
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("loot_drops", sa.Column("rarity_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("loot_drops", "rarity_text")
