"""add account choice to tilerace signups

Revision ID: 0050
Revises: 0049
Create Date: 2026-07-13
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tilerace_signups",
        sa.Column("account_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_tilerace_signups_account",
        "tilerace_signups",
        "user_accounts",
        ["account_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_tilerace_signups_account", "tilerace_signups", type_="foreignkey"
    )
    op.drop_column("tilerace_signups", "account_id")
