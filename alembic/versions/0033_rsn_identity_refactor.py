"""RSN identity refactor: rsn_history on user_accounts, user_account_id FK on event tables

Revision ID: 0033
Revises: 0032
Create Date: 2026-06-08

"""

from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE user_accounts ADD COLUMN rsn_history TEXT[] NOT NULL DEFAULT '{}'"
    )

    op.execute(
        "ALTER TABLE events"
        " ADD COLUMN user_account_id BIGINT REFERENCES user_accounts(id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX ix_events_user_account_id ON events(user_account_id)"
    )

    op.execute(
        "ALTER TABLE coffer_events"
        " ADD COLUMN user_account_id BIGINT REFERENCES user_accounts(id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX ix_coffer_events_user_account_id ON coffer_events(user_account_id)"
    )

    op.execute(
        "ALTER TABLE membership_events"
        " ADD COLUMN user_account_id BIGINT REFERENCES user_accounts(id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX ix_membership_events_user_account_id ON membership_events(user_account_id)"
    )

    # Backfill existing rows using current RSN only (rsn_history is empty for existing rows).
    # Full retroactive backfill via WOM history happens when accounts are linked/refreshed.
    op.execute(
        """
        UPDATE events e
        SET user_account_id = ua.id
        FROM user_accounts ua
        WHERE replace(lower(e.player_name), chr(160), ' ') = lower(ua.rsn)
          AND e.user_account_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE coffer_events ce
        SET user_account_id = ua.id
        FROM user_accounts ua
        WHERE lower(ce.player_name) = lower(ua.rsn)
          AND ce.user_account_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE membership_events me
        SET user_account_id = ua.id
        FROM user_accounts ua
        WHERE lower(me.player_name) = lower(ua.rsn)
          AND me.user_account_id IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_membership_events_user_account_id")
    op.execute("ALTER TABLE membership_events DROP COLUMN IF EXISTS user_account_id")

    op.execute("DROP INDEX IF EXISTS ix_coffer_events_user_account_id")
    op.execute("ALTER TABLE coffer_events DROP COLUMN IF EXISTS user_account_id")

    op.execute("DROP INDEX IF EXISTS ix_events_user_account_id")
    op.execute("ALTER TABLE events DROP COLUMN IF EXISTS user_account_id")

    op.execute("ALTER TABLE user_accounts DROP COLUMN IF EXISTS rsn_history")
