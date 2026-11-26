"""carry frenzy edit grants to frenzy.admin

Revision ID: 0067
Revises: 0066
Create Date: 2026-11-26

The frenzy staff routes check `frenzy.admin` edit. Every role granted `frenzy`
edit is added to `frenzy.admin` edit so no role loses frenzy management. The
downgrade adds the `frenzy.admin` edit roles back onto `frenzy` edit.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None

_CONFIG = sa.table(
    "config",
    sa.column("guild_id", sa.BigInteger),
    sa.column("key", sa.Text),
    sa.column("value", JSONB),
)
_ROW = (_CONFIG.c.guild_id == 0) & (_CONFIG.c.key == "page_permissions")


def merged_grants(value: dict[str, Any], source: str, target: str) -> dict[str, Any]:
    """Return the config with `source` edit roles added to `target` edit."""
    pages = dict(value.get("pages", {}))
    from_roles = pages.get(source, {}).get("edit", [])
    target_page = dict(pages.get(target, {}))
    current = target_page.get("edit", [])
    target_page["edit"] = current + [r for r in from_roles if r not in current]
    pages[target] = target_page
    return {**value, "pages": pages}


def _carry(source: str, target: str) -> None:
    bind = op.get_bind()
    value = bind.execute(sa.select(_CONFIG.c.value).where(_ROW)).scalar_one_or_none()
    if not value:
        return
    merged = merged_grants(value, source, target)
    bind.execute(sa.update(_CONFIG).where(_ROW).values(value=merged))


def upgrade() -> None:
    _carry("frenzy", "frenzy.admin")


def downgrade() -> None:
    _carry("frenzy.admin", "frenzy")
