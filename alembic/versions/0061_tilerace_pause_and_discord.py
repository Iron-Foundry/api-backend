"""tile race roll pause and discord provisioning ids

Revision ID: 0061
Revises: 0060
Create Date: 2026-07-31
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None

_EVENT_COLUMNS = (
    "discord_category_id",
    "discord_captains_role_id",
    "discord_captains_channel_id",
)
_TEAM_COLUMNS = (
    "discord_role_id",
    "discord_text_channel_id",
    "discord_voice_channel_id",
)


def upgrade() -> None:
    op.add_column(
        "tilerace_events",
        sa.Column(
            "rolls_paused",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    for column in _EVENT_COLUMNS:
        op.add_column(
            "tilerace_events", sa.Column(column, sa.BigInteger(), nullable=True)
        )
    for column in _TEAM_COLUMNS:
        op.add_column(
            "tilerace_teams", sa.Column(column, sa.BigInteger(), nullable=True)
        )


def downgrade() -> None:
    for column in _TEAM_COLUMNS:
        op.drop_column("tilerace_teams", column)
    for column in _EVENT_COLUMNS:
        op.drop_column("tilerace_events", column)
    op.drop_column("tilerace_events", "rolls_paused")
