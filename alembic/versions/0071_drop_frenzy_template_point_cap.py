"""drop frenzy template point cap

Revision ID: 0071
Revises: 0070
Create Date: 2026-11-26
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("frenzy_templates", "total_point_cap")


def downgrade() -> None:
    op.add_column(
        "frenzy_templates",
        sa.Column("total_point_cap", sa.Integer(), nullable=False, server_default="0"),
    )
