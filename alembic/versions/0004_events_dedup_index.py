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
    # EXTRACT(EPOCH FROM timestamptz) is STABLE in PG (it checks TimeZone GUC),
    # so we wrap it in an IMMUTABLE function to satisfy index expression requirements.
    # Epoch is always UTC-based so the IMMUTABLE declaration is safe in practice.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION _minute_bucket(ts timestamptz)
        RETURNS bigint LANGUAGE sql IMMUTABLE STRICT
        AS $$ SELECT (EXTRACT(EPOCH FROM ts)::bigint / 60) $$
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX events_dedup_idx
        ON events (player_name, raw_message, _minute_bucket(timestamp))
        WHERE player_name IS NOT NULL AND raw_message IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS events_dedup_idx")
    op.execute("DROP FUNCTION IF EXISTS _minute_bucket(timestamptz)")
