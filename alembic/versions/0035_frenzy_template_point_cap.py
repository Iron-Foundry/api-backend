"""Add total_point_cap column to frenzy_templates.

Revision ID: 0035
Revises: 0034
Create Date: 2026-06-21

"""

from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE frenzy_templates ADD COLUMN total_point_cap INTEGER NOT NULL DEFAULT 0"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE frenzy_templates DROP COLUMN total_point_cap")
