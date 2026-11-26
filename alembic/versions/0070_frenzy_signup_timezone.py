"""frenzy signup timezone

Revision ID: 0070
Revises: 0069
Create Date: 2026-11-26
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0070"
down_revision = "0069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("frenzy_signups", sa.Column("timezone", sa.Text()))


def downgrade() -> None:
    op.drop_column("frenzy_signups", "timezone")
