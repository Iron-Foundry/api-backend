"""add tilerace signup gate and captain opt-in

Revision ID: 0049
Revises: 0048
Create Date: 2026-07-13
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tilerace_events",
        sa.Column("signups_open", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "tilerace_signups",
        sa.Column(
            "wants_captain", sa.Boolean(), nullable=False, server_default="false"
        ),
    )


def downgrade() -> None:
    op.drop_column("tilerace_signups", "wants_captain")
    op.drop_column("tilerace_events", "signups_open")
