"""competition_snapshots: periodic top-5 progress snapshots for timeline charts

Revision ID: 0021
Revises: 0020
Create Date: 2026-05-19

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "competition_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("comp_id", sa.Integer(), nullable=False),
        sa.Column("metric", sa.Text(), nullable=False),
        sa.Column("captured_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("series", JSONB(), server_default="[]", nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_competition_snapshots_lookup",
        "competition_snapshots",
        ["comp_id", "metric", "captured_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_competition_snapshots_lookup", table_name="competition_snapshots")
    op.drop_table("competition_snapshots")
