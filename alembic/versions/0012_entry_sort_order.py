"""add sort_order to content_entries

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-18
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE content_entries
            ADD COLUMN sort_order INT NOT NULL DEFAULT 0;
        CREATE INDEX ON content_entries (category_id, sort_order);
    """)


def downgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS content_entries_category_id_sort_order_idx;
        ALTER TABLE content_entries DROP COLUMN IF EXISTS sort_order;
    """)
