"""add share_token to member_goals

Revision ID: 0038
Revises: 0037
Create Date: 2026-06-26
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "member_goals",
        sa.Column("share_token", UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
    )
    op.create_unique_constraint("uq_member_goals_share_token", "member_goals", ["share_token"])


def downgrade() -> None:
    op.drop_constraint("uq_member_goals_share_token", "member_goals")
    op.drop_column("member_goals", "share_token")
