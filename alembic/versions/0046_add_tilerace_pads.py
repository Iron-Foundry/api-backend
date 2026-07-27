"""add tilerace start and end pads

Revision ID: 0046
Revises: 0045
Create Date: 2026-07-11
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tilerace_events", sa.Column("start_pad", JSONB(), nullable=True))
    op.add_column("tilerace_events", sa.Column("end_pad", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("tilerace_events", "end_pad")
    op.drop_column("tilerace_events", "start_pad")
