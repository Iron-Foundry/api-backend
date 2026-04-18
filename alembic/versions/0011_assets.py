"""assets table

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-18
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE assets (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            filename     TEXT NOT NULL UNIQUE,
            original_name TEXT NOT NULL,
            content_type TEXT NOT NULL,
            size_bytes   BIGINT NOT NULL,
            uploaded_by  BIGINT,
            created_at   TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX ON assets (uploaded_by);
        CREATE INDEX ON assets (created_at DESC);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS assets;")
