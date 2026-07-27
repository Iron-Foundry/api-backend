"""add user_accounts table for multi-RSN support

Revision ID: 0019
Revises: 0018
Create Date: 2026-05-04
"""

import sqlalchemy as sa

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_accounts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("discord_user_id", sa.BigInteger(), nullable=False),
        sa.Column("rsn", sa.Text(), nullable=False),
        sa.Column(
            "is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["discord_user_id"],
            ["users.discord_user_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_user_accounts_discord_user_id",
        "user_accounts",
        ["discord_user_id"],
    )

    # Case-insensitive global RSN uniqueness
    op.execute("CREATE UNIQUE INDEX uq_user_accounts_rsn ON user_accounts (lower(rsn))")

    # One primary per user
    op.execute(
        "CREATE UNIQUE INDEX uq_user_accounts_primary "
        "ON user_accounts (discord_user_id) WHERE is_primary = true"
    )

    # Seed from existing primary RSNs
    op.execute(
        """
        INSERT INTO user_accounts (discord_user_id, rsn, is_primary, created_at)
        SELECT discord_user_id, rsn, true, now()
        FROM users
        WHERE rsn IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_table("user_accounts")
