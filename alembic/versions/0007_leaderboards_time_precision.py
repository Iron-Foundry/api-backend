"""leaderboards: widen time_seconds from INT to NUMERIC(10,3) for ms precision

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-16
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE leaderboards ALTER COLUMN time_seconds TYPE NUMERIC(10,3)")


def downgrade() -> None:
    # Truncates sub-second data - intentional on downgrade
    op.execute(
        "ALTER TABLE leaderboards ALTER COLUMN time_seconds TYPE INT USING time_seconds::INT"
    )
