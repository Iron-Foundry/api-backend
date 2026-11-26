"""point stored osrs-cache image urls at osrsclans

Revision ID: 0066
Revises: 0065
Create Date: 2026-11-26

The `/osrs-cache/*` proxy is gone. Templates, teams, tiles, badges and guide
text hold absolute or relative links to its item icons and sprite frames. Each
becomes the matching OSRSClans image. The downgrade writes the proxy form back
on the production API host, because the original host of a link is not kept.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None

OSRSCLANS = "https://osrsclans.cc/api/v1/osrs"
_PROXY = "https://api.ironfoundry.cc/osrs-cache"
_HOST = "(https?://[^\\s\"'()<>]+)?"

UPGRADE_PAIRS = [
    (
        f"{_HOST}/osrs-cache/item-icons/([0-9]+)(/render\\?size=[0-9]+)?",
        f"{OSRSCLANS}/items/\\2.webp",
    ),
    (
        f"{_HOST}/osrs-cache/sprites/([0-9]+)/([0-9]+)(\\?[^\\s\"'()<>]*)?",
        f"{OSRSCLANS}/sprites/\\2.webp?frame=\\3",
    ),
]
_DOWNGRADE_PAIRS = [
    (f"{OSRSCLANS}/items/([0-9]+)\\.webp", f"{_PROXY}/item-icons/\\1"),
    (
        f"{OSRSCLANS}/sprites/([0-9]+)\\.webp\\?frame=([0-9]+)",
        f"{_PROXY}/sprites/\\1/\\2?format=png",
    ),
]

TEXT_COLUMNS = [
    ("content_entries", "body"),
    ("content_entry_versions", "body"),
    ("feedback_replies", "body"),
    ("badges", "icon"),
    ("frenzy_teams", "icon_url"),
    ("tile_repository_tiles", "icon_url"),
    ("tilerace_events", "background_url"),
    ("tilerace_teams", "icon_url"),
]
JSON_COLUMNS = [
    ("frenzy_templates", "tiers"),
    ("frenzy_template_versions", "tiers"),
]


def _replaced(
    expression: sa.ColumnElement[str], pairs: list[tuple[str, str]]
) -> sa.ColumnElement[str]:
    for pattern, replacement in pairs:
        expression = sa.func.regexp_replace(expression, pattern, replacement, "g")
    return expression


def _text_update(table: str, column: str, pairs: list[tuple[str, str]]) -> sa.Update:
    target = sa.table(table, sa.column(column, sa.Text))
    value = target.c[column]
    return (
        sa.update(target)
        .values({column: _replaced(value, pairs)})
        .where(value.like("%osrs%"))
    )


def _json_update(table: str, column: str, pairs: list[tuple[str, str]]) -> sa.Update:
    target = sa.table(table, sa.column(column, JSONB))
    as_text = sa.cast(target.c[column], sa.Text)
    return (
        sa.update(target)
        .values({column: sa.cast(_replaced(as_text, pairs), JSONB)})
        .where(as_text.like("%osrs%"))
    )


def rewrite_statements(pairs: list[tuple[str, str]]) -> list[sa.Update]:
    """Return one UPDATE per column that applies each (pattern, replacement)."""
    text_updates = [_text_update(t, c, pairs) for t, c in TEXT_COLUMNS]
    return text_updates + [_json_update(t, c, pairs) for t, c in JSON_COLUMNS]


def upgrade() -> None:
    for statement in rewrite_statements(UPGRADE_PAIRS):
        op.execute(statement)


def downgrade() -> None:
    for statement in rewrite_statements(_DOWNGRADE_PAIRS):
        op.execute(statement)
