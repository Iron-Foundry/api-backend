"""add ballot token tables and poll version

Revision ID: 0048
Revises: 0047
Create Date: 2026-07-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "competition_schedules",
        sa.Column("poll_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "competition_schedules",
        sa.Column("token_config_override", JSONB(), nullable=True),
    )
    op.add_column(
        "scheduled_competition_runs",
        sa.Column("tokens_awarded_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "scheduled_competition_runs",
        sa.Column("votes_refunded_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    op.create_table(
        "ballot_token_accounts",
        sa.Column("discord_user_id", sa.BigInteger(), nullable=False),
        sa.Column("balance", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["discord_user_id"], ["users.discord_user_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("discord_user_id"),
    )
    op.create_table(
        "ballot_token_transactions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("discord_user_id", sa.BigInteger(), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"], ["scheduled_competition_runs.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ballot_token_transactions_user",
        "ballot_token_transactions",
        ["discord_user_id"],
    )
    op.create_table(
        "ballot_poll_votes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("discord_user_id", sa.BigInteger(), nullable=False),
        sa.Column("metric", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"], ["scheduled_competition_runs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "discord_user_id", name="uq_ballot_vote_once"),
    )
    op.create_index("ix_ballot_poll_votes_run", "ballot_poll_votes", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_ballot_poll_votes_run", table_name="ballot_poll_votes")
    op.drop_table("ballot_poll_votes")
    op.drop_index(
        "ix_ballot_token_transactions_user",
        table_name="ballot_token_transactions",
    )
    op.drop_table("ballot_token_transactions")
    op.drop_table("ballot_token_accounts")
    op.drop_column("scheduled_competition_runs", "votes_refunded_at")
    op.drop_column("scheduled_competition_runs", "tokens_awarded_at")
    op.drop_column("competition_schedules", "token_config_override")
    op.drop_column("competition_schedules", "poll_version")
