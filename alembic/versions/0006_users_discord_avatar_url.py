"""users: add discord_avatar_url

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-15

"""

import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("discord_avatar_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "discord_avatar_url")
