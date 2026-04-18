"""add content_entry_versions table

Revision ID: 0014
Revises: 0013
Create Date: 2026-04-18
"""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE content_entry_versions (
            id             BIGSERIAL PRIMARY KEY,
            entry_id       UUID NOT NULL REFERENCES content_entries(id) ON DELETE CASCADE,
            version_number INT NOT NULL,
            title          TEXT NOT NULL,
            body           TEXT NOT NULL,
            edited_by      BIGINT,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ON content_entry_versions (entry_id, version_number DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS content_entry_versions")
