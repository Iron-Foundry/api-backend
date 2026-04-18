"""soft delete fields on content_entries

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-18
"""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE content_entries ADD COLUMN deprecated BOOLEAN NOT NULL DEFAULT false")
    op.execute("ALTER TABLE content_entries ADD COLUMN deprecated_at TIMESTAMPTZ")
    op.execute("ALTER TABLE content_entries ADD COLUMN deprecated_by BIGINT")
    op.execute("CREATE INDEX ON content_entries (deprecated) WHERE deprecated = true")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS content_entries_deprecated_idx")
    op.execute("ALTER TABLE content_entries DROP COLUMN IF EXISTS deprecated_by")
    op.execute("ALTER TABLE content_entries DROP COLUMN IF EXISTS deprecated_at")
    op.execute("ALTER TABLE content_entries DROP COLUMN IF EXISTS deprecated")
