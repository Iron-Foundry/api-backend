"""tickets: add added_user_ids to persist ad-hoc invited members across reopen

Reopening a ticket recreates the channel from scratch and only reapplies
permissions for the creator and staff teams, so anyone manually added via
/ticket adduser after creation was silently dropped. Track those ids so
reopen can reinvite them.

Revision ID: 0053
Revises: 0052
Create Date: 2026-07-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tickets",
        sa.Column(
            "added_user_ids",
            sa.ARRAY(sa.BigInteger()),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("tickets", "added_user_ids")
