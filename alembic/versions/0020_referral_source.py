"""users: add referral_source and referral_detail

Revision ID: 0020
Revises: 0019
Create Date: 2026-05-17

"""

from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("referral_source", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("referral_detail", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "referral_source")
    op.drop_column("users", "referral_detail")
