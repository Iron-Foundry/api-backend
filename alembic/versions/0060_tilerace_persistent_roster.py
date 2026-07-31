"""make tilerace signups the persistent roster

Revision ID: 0060
Revises: 0059
Create Date: 2026-07-31
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None

_BACKFILL_SIGNUPS = sa.text("""
    INSERT INTO tilerace_signups (
        event_id, discord_user_id, account_id, rsn, ranking_score,
        wants_captain, is_captain, added_by_staff, team_id, signed_up_at
    )
    SELECT t.event_id,
           (m->>'discord_user_id')::bigint,
           NULL,
           COALESCE(m->>'rsn', ''),
           COALESCE((m->>'ranking_score')::int, 0),
           COALESCE((m->>'is_captain')::boolean, false),
           COALESCE((m->>'is_captain')::boolean, false),
           false,
           t.id,
           now()
    FROM tilerace_teams t
    CROSS JOIN LATERAL jsonb_array_elements(t.members) AS m
    WHERE m->>'discord_user_id' IS NOT NULL
    ON CONFLICT (event_id, discord_user_id) DO UPDATE
       SET team_id = EXCLUDED.team_id,
           is_captain = EXCLUDED.is_captain
""")

_DEDUPE_CAPTAINS = sa.text("""
    UPDATE tilerace_signups s
       SET is_captain = false
     WHERE s.is_captain
       AND (
           s.team_id IS NULL
           OR s.id <> (
               SELECT k.id
                 FROM tilerace_signups k
                WHERE k.team_id = s.team_id AND k.is_captain
                ORDER BY k.ranking_score DESC, k.id
                LIMIT 1
           )
       )
""")

_REBUILD_MEMBERS = sa.text("""
    UPDATE tilerace_teams t
       SET members = COALESCE((
           SELECT jsonb_agg(jsonb_build_object(
                      'discord_user_id', s.discord_user_id::text,
                      'rsn', s.rsn,
                      'ranking_score', s.ranking_score,
                      'is_captain', s.is_captain)
                  ORDER BY s.is_captain DESC, s.ranking_score DESC)
           FROM tilerace_signups s
           WHERE s.team_id = t.id
       ), '[]'::jsonb)
""")


def upgrade() -> None:
    op.add_column(
        "tilerace_events",
        sa.Column("team_size", sa.Integer(), nullable=False, server_default="5"),
    )
    op.add_column(
        "tilerace_signups", sa.Column("team_id", sa.BigInteger(), nullable=True)
    )
    op.create_foreign_key(
        "fk_tilerace_signup_team",
        "tilerace_signups",
        "tilerace_teams",
        ["team_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "tilerace_signups",
        sa.Column(
            "is_captain", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column(
        "tilerace_signups",
        sa.Column(
            "added_by_staff",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.execute(_BACKFILL_SIGNUPS)
    op.execute(_DEDUPE_CAPTAINS)
    op.create_index(
        "uq_tilerace_team_captain",
        "tilerace_signups",
        ["team_id"],
        unique=True,
        postgresql_where=sa.text("is_captain AND team_id IS NOT NULL"),
    )
    op.drop_column("tilerace_teams", "members")


def downgrade() -> None:
    op.add_column(
        "tilerace_teams",
        sa.Column(
            "members",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.execute(_REBUILD_MEMBERS)
    op.drop_index("uq_tilerace_team_captain", table_name="tilerace_signups")
    op.drop_constraint(
        "fk_tilerace_signup_team", "tilerace_signups", type_="foreignkey"
    )
    op.drop_column("tilerace_signups", "added_by_staff")
    op.drop_column("tilerace_signups", "is_captain")
    op.drop_column("tilerace_signups", "team_id")
    op.drop_column("tilerace_events", "team_size")
