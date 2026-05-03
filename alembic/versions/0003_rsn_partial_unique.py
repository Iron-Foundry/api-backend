"""users.rsn: replace NULLS NOT DISTINCT unique constraint with partial unique index

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-15

"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the NULLS NOT DISTINCT constraint that prevents multiple NULL rsn values
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_rsn_unique")
    # Partial unique index - only enforces uniqueness when rsn is set
    op.execute(
        "CREATE UNIQUE INDEX users_rsn_unique ON users (rsn) WHERE rsn IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS users_rsn_unique")
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT users_rsn_unique UNIQUE NULLS NOT DISTINCT (rsn)"
    )
