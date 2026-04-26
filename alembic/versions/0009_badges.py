"""Add badges and user_badges tables."""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE badges (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name        TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            icon        TEXT,
            color       TEXT NOT NULL DEFAULT '#6366f1',
            text_color  TEXT NOT NULL DEFAULT '#ffffff',
            created_at  TIMESTAMPTZ DEFAULT NOW(),
            created_by  BIGINT
        )
    """)
    op.execute("""
        CREATE TABLE user_badges (
            id               BIGSERIAL PRIMARY KEY,
            badge_id         UUID NOT NULL REFERENCES badges(id) ON DELETE CASCADE,
            discord_user_id  BIGINT NOT NULL,
            assigned_at      TIMESTAMPTZ DEFAULT NOW(),
            assigned_by      BIGINT,
            UNIQUE (badge_id, discord_user_id)
        )
    """)
    op.execute("CREATE INDEX ON user_badges (discord_user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE user_badges")
    op.execute("DROP TABLE badges")
