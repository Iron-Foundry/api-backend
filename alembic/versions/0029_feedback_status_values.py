"""update feedback status check constraint to new values

Revision ID: 0029
Revises: 0028
Create Date: 2026-06-02
"""

from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

_NEW = "status IN ('open', 'planned', 'implemented', 'needs-triage', 'wont-add', 'reviewing', 'patched', 'wont-fix')"
_OLD = "status IN ('open', 'in-review', 'implemented', 'wont-fix', 'solved', 'closed')"


def upgrade() -> None:
    op.drop_constraint("ck_feedback_status", "feedback")
    op.execute(f"ALTER TABLE feedback ADD CONSTRAINT ck_feedback_status CHECK ({_NEW})")
    # Migrate any rows using removed statuses to nearest equivalent
    op.execute("UPDATE feedback SET status = 'reviewing' WHERE status = 'in-review'")
    op.execute("UPDATE feedback SET status = 'patched'   WHERE status = 'solved'")
    op.execute("UPDATE feedback SET status = 'open'      WHERE status = 'closed'")


def downgrade() -> None:
    op.drop_constraint("ck_feedback_status", "feedback")
    op.execute(f"ALTER TABLE feedback ADD CONSTRAINT ck_feedback_status CHECK ({_OLD})")
    op.execute("UPDATE feedback SET status = 'in-review' WHERE status = 'reviewing'")
    op.execute("UPDATE feedback SET status = 'solved'    WHERE status = 'patched'")
    op.execute("UPDATE feedback SET status = 'open'      WHERE status = 'needs-triage'")
    op.execute("UPDATE feedback SET status = 'closed'    WHERE status = 'wont-add'")
