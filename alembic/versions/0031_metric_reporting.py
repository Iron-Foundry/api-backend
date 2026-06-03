"""metric reporting tables

Revision ID: 0031
Revises: 0030
Create Date: 2026-06-03

"""

from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE service_status (
            service_name    TEXT        PRIMARY KEY,
            is_healthy      BOOLEAN     NOT NULL,
            last_seen       TIMESTAMPTZ NOT NULL,
            version         TEXT,
            uptime_seconds  BIGINT,
            summary_metrics JSONB       NOT NULL DEFAULT '{}'
        )
    """)

    op.execute("""
        CREATE TABLE metric_records (
            id           BIGSERIAL   PRIMARY KEY,
            service_name TEXT        NOT NULL,
            module_name  TEXT        NOT NULL,
            recorded_at  TIMESTAMPTZ NOT NULL,
            metrics      JSONB       NOT NULL DEFAULT '{}'
        )
    """)
    op.execute(
        "CREATE INDEX ix_metric_records_lookup"
        " ON metric_records (service_name, module_name, recorded_at DESC)"
    )

    op.execute("""
        CREATE TABLE metric_records_compact (
            id           BIGSERIAL PRIMARY KEY,
            service_name TEXT      NOT NULL,
            module_name  TEXT      NOT NULL,
            date         DATE      NOT NULL,
            sample_count INT       NOT NULL,
            metrics_agg  JSONB     NOT NULL DEFAULT '{}',
            CONSTRAINT uq_metric_compact_day UNIQUE (service_name, module_name, date)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS metric_records_compact")
    op.execute("DROP TABLE IF EXISTS metric_records")
    op.execute("DROP TABLE IF EXISTS service_status")
