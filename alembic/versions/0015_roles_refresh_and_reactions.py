"""add roles_fetched_at to users and content_entry_reactions table

Revision ID: 0015
Revises: 0014
Create Date: 2026-04-21
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Auto role refresh: track when discord roles were last fetched
    op.add_column(
        "users",
        sa.Column("roles_fetched_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    # Content entry reactions
    op.create_table(
        "content_entry_reactions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("entry_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("discord_user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["content_entries.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entry_id", "discord_user_id", name="uq_content_entry_reaction"
        ),
    )
    op.create_index(
        "ix_content_entry_reactions_entry_id",
        "content_entry_reactions",
        ["entry_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_content_entry_reactions_entry_id", "content_entry_reactions")
    op.drop_table("content_entry_reactions")
    op.drop_column("users", "roles_fetched_at")
