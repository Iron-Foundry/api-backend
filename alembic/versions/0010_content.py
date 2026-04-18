"""Add content_categories, content_entries, content_collaborators tables."""
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE content_categories (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            page_type   TEXT NOT NULL,
            parent_id   UUID REFERENCES content_categories(id) ON DELETE CASCADE,
            slug        TEXT NOT NULL,
            label       TEXT NOT NULL,
            sort_order  INT NOT NULL DEFAULT 0,
            created_at  TIMESTAMPTZ DEFAULT NOW(),
            created_by  BIGINT,
            UNIQUE (page_type, parent_id, slug)
        )
    """)
    op.execute("CREATE INDEX ON content_categories (page_type)")
    op.execute("CREATE INDEX ON content_categories (parent_id)")

    op.execute("""
        CREATE TABLE content_entries (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            category_id UUID NOT NULL REFERENCES content_categories(id) ON DELETE CASCADE,
            slug        TEXT NOT NULL,
            title       TEXT NOT NULL,
            body        TEXT NOT NULL DEFAULT '',
            created_by  BIGINT,
            created_at  TIMESTAMPTZ DEFAULT NOW(),
            updated_at  TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (category_id, slug)
        )
    """)
    op.execute("CREATE INDEX ON content_entries (category_id)")

    op.execute("""
        CREATE TABLE content_collaborators (
            id              BIGSERIAL PRIMARY KEY,
            entry_id        UUID NOT NULL REFERENCES content_entries(id) ON DELETE CASCADE,
            discord_user_id BIGINT NOT NULL,
            added_at        TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (entry_id, discord_user_id)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE content_collaborators")
    op.execute("DROP TABLE content_entries")
    op.execute("DROP TABLE content_categories")
