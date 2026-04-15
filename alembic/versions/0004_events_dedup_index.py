"""events: add partial unique index to prevent duplicate broadcast events

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-15

"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Prevent duplicate broadcast events within the same minute.
    # Legitimate repeat events (e.g. same drop twice) are extremely unlikely
    # within the same minute. This index is the last-resort safety net;
    # primary dedup is handled by Valkey TTL in the dispatcher.
    op.execute(
        """
        CREATE UNIQUE INDEX events_dedup_idx
        ON events (player_name, raw_message, (EXTRACT(EPOCH FROM timestamp)::bigint / 60))
        WHERE player_name IS NOT NULL AND raw_message IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS events_dedup_idx")
