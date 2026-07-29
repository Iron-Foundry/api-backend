"""carry cover art on saved playlist tracks

Revision ID: 0058
Revises: 0057
Create Date: 2026-07-29
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("playlist_tracks", sa.Column("artwork", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("playlist_tracks", "artwork")
