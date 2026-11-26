"""drop the wiki loot scrape tables

Revision ID: 0065
Revises: 0064
Create Date: 2026-11-26

Loot rates come from OSRSClans. The downgrade recreates both tables empty, as
0054 to 0056 left them.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_loot_drops_item_id", table_name="loot_drops")
    op.drop_index("ix_loot_drops_source_slug", table_name="loot_drops")
    op.drop_table("loot_drops")
    op.drop_index("ix_loot_sources_category", table_name="loot_sources")
    op.drop_table("loot_sources")


def downgrade() -> None:
    op.create_table(
        "loot_sources",
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("wiki_page", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("reward_kind", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("slug"),
    )
    op.create_index("ix_loot_sources_category", "loot_sources", ["category"])
    op.create_table(
        "loot_drops",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_slug", sa.Text(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=True),
        sa.Column("item_name", sa.Text(), nullable=False),
        sa.Column("quantity_low", sa.Integer(), nullable=False),
        sa.Column("quantity_high", sa.Integer(), nullable=False),
        sa.Column("noted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rarity_num", sa.Integer(), nullable=True),
        sa.Column("rarity_denom", sa.Integer(), nullable=True),
        sa.Column("rolls", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("drop_group", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("rarity_text", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["source_slug"], ["loot_sources.slug"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_loot_drops_source_slug", "loot_drops", ["source_slug"])
    op.create_index("ix_loot_drops_item_id", "loot_drops", ["item_id"])
