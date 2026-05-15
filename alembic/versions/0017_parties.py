"""add parties, party_members, and party_chat_messages tables

Revision ID: 0017
Revises: 0016
Create Date: 2026-04-29
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "parties",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("leader_id", sa.Text(), nullable=False),
        sa.Column("leader_username", sa.Text(), nullable=False),
        sa.Column("leader_rsn", sa.Text(), nullable=True),
        sa.Column("activity", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("vibe", sa.Text(), nullable=False, server_default="chill"),
        sa.Column("max_size", sa.Integer(), nullable=False),
        sa.Column("ping_role_ids", JSONB(), nullable=False, server_default="[]"),
        sa.Column("hub_code", sa.Text(), nullable=False),
        sa.Column("discord_message_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("scheduled_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_parties_status", "parties", ["status"])
    op.create_index("ix_parties_expires_at", "parties", ["expires_at"])

    op.create_table(
        "party_members",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("party_id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("rsn", sa.Text(), nullable=True),
        sa.Column("joined_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["party_id"], ["parties.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("party_id", "user_id"),
    )
    op.create_index("ix_party_members_party_id", "party_members", ["party_id"])

    op.create_table(
        "party_chat_messages",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("party_id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("rsn", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["party_id"], ["parties.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_party_chat_messages_party_sent",
        "party_chat_messages",
        ["party_id", "sent_at"],
    )


def downgrade() -> None:
    op.drop_table("party_chat_messages")
    op.drop_table("party_members")
    op.drop_table("parties")
