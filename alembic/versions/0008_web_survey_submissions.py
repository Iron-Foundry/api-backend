"""web_survey_submissions: web-submitted survey/application responses

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-17
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE web_survey_submissions (
            id BIGSERIAL PRIMARY KEY,
            template_id TEXT NOT NULL,
            discord_user_id BIGINT NOT NULL,
            answers JSONB NOT NULL DEFAULT '{}',
            submitted_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (template_id, discord_user_id)
        )
    """)
    op.execute("CREATE INDEX ON web_survey_submissions (template_id)")
    op.execute("CREATE INDEX ON web_survey_submissions (discord_user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE web_survey_submissions")
