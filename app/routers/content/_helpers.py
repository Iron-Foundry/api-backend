from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContentCategory, ContentEntry
from app.dependencies import (
    get_current_user as _get_current_user,  # noqa: F401 re-export
)
from app.services.page_permissions import check_page_permission
from app.services.rank_mappings import get_effective_roles

_VALID_PAGE_TYPES = {"plugin", "resource", "staff_resource"}

_PAGE_TYPE_TO_PAGE_ID: dict[str, str] = {
    "resource": "resources",
    "plugin": "plugins",
    "staff_resource": "staff.resources",
}


def _slugify(label: str) -> str:
    s = label.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-") or "category"


def _validate_page_type(page_type: str) -> None:
    if page_type not in _VALID_PAGE_TYPES:
        raise HTTPException(404, f"Unknown page type '{page_type}'.")


async def _require_mentor(
    current_user: dict[str, Any], session: AsyncSession, page_type: str = "resource"
) -> None:
    uid = int(current_user["sub"])
    roles = await get_effective_roles(uid, session)
    page_id = _PAGE_TYPE_TO_PAGE_ID.get(page_type, "resources")
    if not await check_page_permission(page_id, "create", roles, session):
        raise HTTPException(403, "Requires Foundry Mentors or higher.")


async def _require_senior_mod(
    current_user: dict[str, Any], session: AsyncSession, page_type: str = "resource"
) -> None:
    uid = int(current_user["sub"])
    roles = await get_effective_roles(uid, session)
    page_id = _PAGE_TYPE_TO_PAGE_ID.get(page_type, "resources")
    if not await check_page_permission(page_id, "delete", roles, session):
        raise HTTPException(403, "Requires Senior Moderator or higher.")


async def _slug_exists_in_page_type(
    slug: str,
    page_type: str,
    session: AsyncSession,
    exclude_entry_id: UUID | None = None,
) -> bool:
    stmt = (
        select(ContentEntry.id)
        .join(ContentCategory, ContentEntry.category_id == ContentCategory.id)
        .where(ContentCategory.page_type == page_type, ContentEntry.slug == slug)
    )
    if exclude_entry_id is not None:
        stmt = stmt.where(ContentEntry.id != exclude_entry_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None
