"""replace ping_role_ids with notification_category_ids, add party_notification_preferences

Revision ID: 0022
Revises: 0021
Create Date: 2026-05-28
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "parties",
        sa.Column(
            "notification_category_ids",
            JSONB(),
            nullable=False,
            server_default="[]",
        ),
    )
    op.drop_column("parties", "ping_role_ids")

    op.create_table(
        "party_notification_preferences",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("category_ids", JSONB(), nullable=False, server_default="[]"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("party_notification_preferences")
    op.add_column(
        "parties",
        sa.Column("ping_role_ids", JSONB(), nullable=False, server_default="[]"),
    )
    op.drop_column("parties", "notification_category_ids")
