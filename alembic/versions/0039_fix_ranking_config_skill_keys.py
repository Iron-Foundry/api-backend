"""fix ranking_config skill keys: range->ranged, defense->defence

Revision ID: 0039
Revises: 0038
Create Date: 2026-06-26
"""

from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE config
        SET value = jsonb_set(
            value,
            '{skills}',
            (
                SELECT jsonb_agg(
                    CASE
                        WHEN elem::text = '"range"'   THEN '"ranged"'::jsonb
                        WHEN elem::text = '"defense"' THEN '"defence"'::jsonb
                        ELSE elem
                    END
                )
                FROM jsonb_array_elements(value->'skills') AS elem
            )
        )
        WHERE guild_id = 0
          AND key = 'ranking_config'
          AND value ? 'skills'
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE config
        SET value = jsonb_set(
            value,
            '{skills}',
            (
                SELECT jsonb_agg(
                    CASE
                        WHEN elem::text = '"ranged"'  THEN '"range"'::jsonb
                        WHEN elem::text = '"defence"' THEN '"defense"'::jsonb
                        ELSE elem
                    END
                )
                FROM jsonb_array_elements(value->'skills') AS elem
            )
        )
        WHERE guild_id = 0
          AND key = 'ranking_config'
          AND value ? 'skills'
    """)
