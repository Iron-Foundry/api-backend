"""Add competition_schedules and scheduled_competition_runs tables.

Revision ID: 0034
Revises: 0033
Create Date: 2026-06-11

"""

from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE competition_schedules (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            poll_channel_id BIGINT NOT NULL,
            results_channel_id BIGINT NOT NULL,
            poll_duration_hours FLOAT NOT NULL,
            competition_duration_hours FLOAT NOT NULL,
            recurrence_days FLOAT NOT NULL,
            poll_options JSONB NOT NULL DEFAULT '[]',
            title_template TEXT NOT NULL DEFAULT '{metric} Competition',
            next_poll_at TIMESTAMPTZ,
            created_by BIGINT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE scheduled_competition_runs (
            id BIGSERIAL PRIMARY KEY,
            schedule_id BIGINT NOT NULL REFERENCES competition_schedules(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'pending_poll',
            poll_options_override JSONB,
            discord_poll_message_id BIGINT,
            discord_poll_channel_id BIGINT,
            winning_metric TEXT,
            wom_competition_id INTEGER,
            competition_title TEXT,
            poll_starts_at TIMESTAMPTZ,
            poll_ends_at TIMESTAMPTZ,
            competition_starts_at TIMESTAMPTZ,
            competition_ends_at TIMESTAMPTZ,
            error_detail TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute(
        "CREATE INDEX ix_scheduled_competition_runs_schedule_status "
        "ON scheduled_competition_runs(schedule_id, status)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scheduled_competition_runs")
    op.execute("DROP TABLE IF EXISTS competition_schedules")
