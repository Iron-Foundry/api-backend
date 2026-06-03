"""rename is_official to is_pinned in feedback_replies, drop one-official constraint

Revision ID: 0028
Revises: 0027
Create Date: 2026-06-02
"""

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_feedback_replies_official")
    op.alter_column("feedback_replies", "is_official", new_column_name="is_pinned")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_feedback_replies_pinned
        ON feedback_replies (feedback_id)
        WHERE is_pinned = true
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_feedback_replies_pinned")
    op.alter_column("feedback_replies", "is_pinned", new_column_name="is_official")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_feedback_replies_official
        ON feedback_replies (feedback_id)
        WHERE is_official = true
        """
    )
