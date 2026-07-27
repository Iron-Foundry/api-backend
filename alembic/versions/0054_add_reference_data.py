"""add loot table and efficiency rate reference tables

Revision ID: 0054
Revises: 0053
Create Date: 2026-07-26
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "loot_sources",
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("wiki_page", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["source_slug"], ["loot_sources.slug"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_loot_drops_source_slug", "loot_drops", ["source_slug"])
    op.create_index("ix_loot_drops_item_id", "loot_drops", ["item_id"])

    op.create_table(
        "efficiency_rates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("metric", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("rate", sa.Float(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("metric", "kind", name="uq_efficiency_metric_kind"),
    )
    op.create_index("ix_efficiency_rates_metric", "efficiency_rates", ["metric"])


def downgrade() -> None:
    op.drop_index("ix_efficiency_rates_metric", table_name="efficiency_rates")
    op.drop_table("efficiency_rates")
    op.drop_index("ix_loot_drops_item_id", table_name="loot_drops")
    op.drop_index("ix_loot_drops_source_slug", table_name="loot_drops")
    op.drop_table("loot_drops")
    op.drop_index("ix_loot_sources_category", table_name="loot_sources")
    op.drop_table("loot_sources")
