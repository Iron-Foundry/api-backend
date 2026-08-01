"""tile race managed-channel permission toggles

Revision ID: 0062
Revises: 0061
Create Date: 2026-08-01
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tilerace_events",
        sa.Column(
            "discord_permissions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("tilerace_events", "discord_permissions")
