"""drop the Explv map tile cache table

The map is now owned by osrs-cache-service, which bakes and serves its own tiles.
api-backend no longer proxies or caches Explv tiles, so the table and its indexes go.

Revision ID: 0052
Revises: 0051
Create Date: 2026-07-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_map_tiles_z_content", table_name="map_tiles")
    op.drop_index("ix_map_tiles_content", table_name="map_tiles")
    op.drop_index("ix_map_tiles_region", table_name="map_tiles")
    op.drop_table("map_tiles")


def downgrade() -> None:
    op.create_table(
        "map_tiles",
        sa.Column("plane", sa.SmallInteger(), nullable=False),
        sa.Column("z", sa.SmallInteger(), nullable=False),
        sa.Column("x", sa.Integer(), nullable=False),
        sa.Column("y", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("content_type", sa.String(32), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("dominant_color", sa.String(7), nullable=True),
        sa.Column("has_content", sa.Boolean(), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=True),
        sa.Column("fetched_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("plane", "z", "x", "y"),
    )
    op.create_index(
        "ix_map_tiles_region",
        "map_tiles",
        ["region_id"],
        postgresql_where=sa.text("region_id IS NOT NULL"),
    )
    op.create_index(
        "ix_map_tiles_content",
        "map_tiles",
        ["plane", "z"],
        postgresql_where=sa.text("has_content = true"),
    )
    op.create_index(
        "ix_map_tiles_z_content",
        "map_tiles",
        ["z", "has_content"],
    )
