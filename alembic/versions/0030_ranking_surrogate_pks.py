"""replace RSN primary keys with surrogate integer PKs on ranking tables

Revision ID: 0030
Revises: 0029
Create Date: 2026-06-03
"""

import sqlalchemy as sa

from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- player_rankings ---
    op.add_column(
        "player_rankings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=True),
    )
    op.execute("CREATE SEQUENCE IF NOT EXISTS player_rankings_id_seq")
    op.execute("UPDATE player_rankings SET id = nextval('player_rankings_id_seq')")
    op.alter_column("player_rankings", "id", nullable=False)
    op.execute("ALTER SEQUENCE player_rankings_id_seq OWNED BY player_rankings.id")
    op.drop_constraint("player_rankings_pkey", "player_rankings", type_="primary")
    op.create_primary_key("player_rankings_pkey", "player_rankings", ["id"])
    op.create_unique_constraint("uq_player_rankings_rsn", "player_rankings", ["rsn"])

    # --- player_snapshots ---
    op.add_column(
        "player_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=True),
    )
    op.execute("CREATE SEQUENCE IF NOT EXISTS player_snapshots_id_seq")
    op.execute("UPDATE player_snapshots SET id = nextval('player_snapshots_id_seq')")
    op.alter_column("player_snapshots", "id", nullable=False)
    op.execute("ALTER SEQUENCE player_snapshots_id_seq OWNED BY player_snapshots.id")
    op.drop_constraint("player_snapshots_pkey", "player_snapshots", type_="primary")
    op.create_primary_key("player_snapshots_pkey", "player_snapshots", ["id"])
    op.create_unique_constraint("uq_player_snapshots_rsn", "player_snapshots", ["rsn"])


def downgrade() -> None:
    # --- player_snapshots ---
    op.drop_constraint("uq_player_snapshots_rsn", "player_snapshots", type_="unique")
    op.drop_constraint("player_snapshots_pkey", "player_snapshots", type_="primary")
    op.create_primary_key("player_snapshots_pkey", "player_snapshots", ["rsn"])
    op.drop_column("player_snapshots", "id")
    op.execute("DROP SEQUENCE IF EXISTS player_snapshots_id_seq")

    # --- player_rankings ---
    op.drop_constraint("uq_player_rankings_rsn", "player_rankings", type_="unique")
    op.drop_constraint("player_rankings_pkey", "player_rankings", type_="primary")
    op.create_primary_key("player_rankings_pkey", "player_rankings", ["rsn"])
    op.drop_column("player_rankings", "id")
    op.execute("DROP SEQUENCE IF EXISTS player_rankings_id_seq")
