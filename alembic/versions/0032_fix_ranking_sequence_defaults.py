"""fix missing DEFAULT on player_rankings and player_snapshots id columns

Revision ID: 0032
Revises: 0031
Create Date: 2026-06-03
"""

from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE player_rankings ALTER COLUMN id"
        " SET DEFAULT nextval('player_rankings_id_seq')"
    )
    op.execute(
        "ALTER TABLE player_snapshots ALTER COLUMN id"
        " SET DEFAULT nextval('player_snapshots_id_seq')"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE player_rankings ALTER COLUMN id DROP DEFAULT")
    op.execute("ALTER TABLE player_snapshots ALTER COLUMN id DROP DEFAULT")
