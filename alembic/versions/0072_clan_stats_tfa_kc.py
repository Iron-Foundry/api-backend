"""clan stats tfa kc

Revision ID: 0072
Revises: 0071
Create Date: 2026-11-26
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0072"
down_revision = "0071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clan_stats", sa.Column("tfa_kc", sa.Integer()))


def downgrade() -> None:
    op.drop_column("clan_stats", "tfa_kc")
