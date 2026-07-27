"""add feedback, feedback_reactions, and feedback_replies tables

Revision ID: 0026
Revises: 0025
Create Date: 2026-06-02
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feedback",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        # suggestion | bug
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("discord_user_id", sa.BigInteger(), nullable=False),
        sa.Column("is_anonymous", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        # { steps_to_reproduce } for bugs; {} for suggestions
        sa.Column("extra", JSONB(), nullable=False, server_default="{}"),
        # open | in-review | implemented | wont-fix | solved | closed
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint(
            "type IN ('suggestion', 'bug')",
            name="ck_feedback_type",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'in-review', 'implemented', 'wont-fix', 'solved', 'closed')",
            name="ck_feedback_status",
        ),
    )
    op.create_index("ix_feedback_type_status", "feedback", ["type", "status"])
    op.create_index("ix_feedback_discord_user", "feedback", ["discord_user_id"])

    op.create_table(
        "feedback_reactions",
        sa.Column(
            "feedback_id",
            sa.BigInteger(),
            sa.ForeignKey("feedback.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column("discord_user_id", sa.BigInteger(), nullable=False, primary_key=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_feedback_reactions_feedback_id", "feedback_reactions", ["feedback_id"]
    )

    op.create_table(
        "feedback_replies",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "feedback_id",
            sa.BigInteger(),
            sa.ForeignKey("feedback.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("discord_user_id", sa.BigInteger(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_official", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_feedback_replies_feedback_id", "feedback_replies", ["feedback_id"]
    )
    # Only one official reply per feedback item
    op.execute(
        """
        CREATE UNIQUE INDEX uq_feedback_replies_official
        ON feedback_replies (feedback_id)
        WHERE is_official = true
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_feedback_replies_official")
    op.drop_index("ix_feedback_replies_feedback_id", "feedback_replies")
    op.drop_table("feedback_replies")

    op.drop_index("ix_feedback_reactions_feedback_id", "feedback_reactions")
    op.drop_table("feedback_reactions")

    op.drop_index("ix_feedback_discord_user", "feedback")
    op.drop_index("ix_feedback_type_status", "feedback")
    op.drop_table("feedback")
