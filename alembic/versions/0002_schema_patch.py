"""schema patch: tickets.timeout_frozen, tickets.metadata, events.discord_user_id, role_panels

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-14

"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── tickets: add timeout_frozen + metadata ──────────────────────────────
    op.execute(
        "ALTER TABLE tickets ADD COLUMN timeout_frozen BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute("ALTER TABLE tickets ADD COLUMN metadata JSONB NOT NULL DEFAULT '{}'")

    # ── events: add discord_user_id (nullable, no FK — RSN changes) ─────────
    op.execute("ALTER TABLE events ADD COLUMN discord_user_id BIGINT")
    op.execute("CREATE INDEX events_user ON events (discord_user_id)")

    # ── role_panels ─────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE role_panels (
            panel_id       TEXT        PRIMARY KEY,
            guild_id       BIGINT      NOT NULL,
            channel_id     BIGINT      NOT NULL,
            message_id     BIGINT      NOT NULL,
            title          TEXT        NOT NULL,
            description    TEXT        NOT NULL DEFAULT '',
            max_selectable INT,
            roles          JSONB       NOT NULL DEFAULT '[]',
            created_at     TIMESTAMPTZ NOT NULL,
            updated_at     TIMESTAMPTZ NOT NULL
        )
    """)
    op.execute("CREATE INDEX role_panels_guild ON role_panels (guild_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS role_panels")
    op.execute("DROP INDEX IF EXISTS events_user")
    op.execute("ALTER TABLE events DROP COLUMN IF EXISTS discord_user_id")
    op.execute("ALTER TABLE tickets DROP COLUMN IF EXISTS metadata")
    op.execute("ALTER TABLE tickets DROP COLUMN IF EXISTS timeout_frozen")
