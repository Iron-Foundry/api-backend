"""add attachment_ids to feedback table

Revision ID: 0027
Revises: 0026
Create Date: 2026-06-02
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "feedback",
        sa.Column("attachment_ids", JSONB, nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("feedback", "attachment_ids")
