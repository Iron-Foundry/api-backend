"""users: add hide_presence_notifications, recruited_by, join_date; events: replace discord_user_id with user_id FK

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-15

"""

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # users: new columns
    op.add_column(
        "users",
        sa.Column(
            "hide_presence_notifications",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "users",
        sa.Column("recruited_by", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("join_date", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.execute("UPDATE users SET join_date = created_at WHERE join_date IS NULL")

    # events: replace discord_user_id with user_id (FK → users, indexed)
    op.drop_column("events", "discord_user_id")
    op.add_column(
        "events",
        sa.Column("user_id", sa.BigInteger(), nullable=True),
    )
    op.create_index("ix_events_user_id", "events", ["user_id"])

    # Backfill user_id from users.rsn matched case-insensitively to events.player_name
    op.execute(
        """
        UPDATE events e
        SET user_id = u.discord_user_id
        FROM users u
        WHERE u.rsn IS NOT NULL
          AND lower(e.player_name) = lower(u.rsn)
        """
    )

    # Backfill total_clogs metric from existing collection_log events
    op.execute(
        """
        INSERT INTO metrics (id, count, last_updated)
        SELECT 'total_clogs', COUNT(*), NOW()
        FROM events
        WHERE type = 'collection_log'
        ON CONFLICT (id) DO UPDATE
            SET count = EXCLUDED.count, last_updated = EXCLUDED.last_updated
        """
    )

    # Backfill users.ticket_ids from tickets.creator_id
    op.execute(
        """
        UPDATE users u
        SET ticket_ids = t.ids
        FROM (
            SELECT creator_id, array_agg(ticket_id ORDER BY ticket_id) AS ids
            FROM tickets
            GROUP BY creator_id
        ) t
        WHERE t.creator_id = u.discord_user_id
        """
    )


def downgrade() -> None:
    op.drop_column("users", "hide_presence_notifications")
    op.drop_column("users", "recruited_by")
    op.drop_column("users", "join_date")

    op.drop_index("ix_events_user_id", table_name="events")
    op.drop_column("events", "user_id")
    op.add_column(
        "events",
        sa.Column("discord_user_id", sa.BigInteger(), nullable=True),
    )
