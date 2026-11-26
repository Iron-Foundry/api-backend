"""osrsclans images via foundry

Revision ID: 0073
Revises: 0072
Create Date: 2026-11-26

Templates, teams, tiles, badges and guide text hold OSRSClans image links. Each
becomes the matching link on Foundry's image route, which keeps a copy of the
image, at the API address in `PUBLIC_API_URL`. The downgrade writes the OSRSClans
form back.
"""

from __future__ import annotations

import os
import re

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None

OSRSCLANS = "https://osrsclans.cc/api/v1/osrs"
ROUTE = "/reference/osrs/images"
_KINDS = "(items|npcs|sprites)"

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


def _public_api_url() -> str:
    url = os.environ.get("PUBLIC_API_URL", "").rstrip("/")
    if not url:
        raise RuntimeError("PUBLIC_API_URL must be set to rewrite image links")
    return url


def upgrade_pair(public: str) -> tuple[str, str]:
    """Return the (pattern, replacement) that points OSRSClans links at Foundry."""
    return (f"{re.escape(OSRSCLANS)}/{_KINDS}/", f"{public}{ROUTE}/\\1/")


def downgrade_pair(public: str) -> tuple[str, str]:
    """Return the (pattern, replacement) that points Foundry links back at OSRSClans."""
    return (f"{re.escape(public + ROUTE)}/{_KINDS}/", f"{OSRSCLANS}/\\1/")


def _text_update(table: str, column: str, pair: tuple[str, str]) -> sa.Update:
    target = sa.table(table, sa.column(column, sa.Text))
    value = target.c[column]
    return (
        sa.update(target)
        .values({column: sa.func.regexp_replace(value, *pair, "g")})
        .where(value.op("~")(pair[0]))
    )


def _json_update(table: str, column: str, pair: tuple[str, str]) -> sa.Update:
    target = sa.table(table, sa.column(column, JSONB))
    as_text = sa.cast(target.c[column], sa.Text)
    rewritten = sa.func.regexp_replace(as_text, *pair, "g")
    return (
        sa.update(target)
        .values({column: sa.cast(rewritten, JSONB)})
        .where(as_text.op("~")(pair[0]))
    )


def rewrite_statements(pair: tuple[str, str]) -> list[sa.Update]:
    """Return one UPDATE per column that applies the (pattern, replacement)."""
    text_updates = [_text_update(t, c, pair) for t, c in TEXT_COLUMNS]
    return text_updates + [_json_update(t, c, pair) for t, c in JSON_COLUMNS]


def upgrade() -> None:
    for statement in rewrite_statements(upgrade_pair(_public_api_url())):
        op.execute(statement)


def downgrade() -> None:
    for statement in rewrite_statements(downgrade_pair(_public_api_url())):
        op.execute(statement)
