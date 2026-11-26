"""frenzy event signups

Revision ID: 0068
Revises: 0067
Create Date: 2026-11-26
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "frenzy_events",
        sa.Column(
            "signups_open", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.create_table(
        "frenzy_signups",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "event_id",
            sa.BigInteger(),
            sa.ForeignKey("frenzy_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("discord_user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "account_id",
            sa.BigInteger(),
            sa.ForeignKey("user_accounts.id", ondelete="SET NULL"),
        ),
        sa.Column("rsn", sa.Text(), nullable=False),
        sa.Column("signed_up_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.UniqueConstraint("event_id", "discord_user_id", name="uq_frenzy_signup"),
    )


def downgrade() -> None:
    op.drop_table("frenzy_signups")
    op.drop_column("frenzy_events", "signups_open")
