from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Badge
from app.services.page_permissions import check_page_permission
from app.services.rank_mappings import get_effective_roles


class BadgeBody(BaseModel):
    name: str
    description: str = ""
    icon: str | None = None
    color: str = "#6366f1"
    text_color: str = "#ffffff"


class AssignBody(BaseModel):
    discord_user_id: int


def serialize_badge(b: Badge) -> dict[str, Any]:
    return {
        "id": str(b.id),
        "name": b.name,
        "description": b.description,
        "icon": b.icon,
        "color": b.color,
        "text_color": b.text_color,
        "created_at": b.created_at.isoformat() if b.created_at else None,
    }


async def require_mentor(current_user: dict[str, Any], session: AsyncSession) -> None:
    uid = int(current_user["sub"])
    roles = await get_effective_roles(uid, session)
    if not await check_page_permission("staff.badges", "create", roles, session):
        raise HTTPException(403, "Requires Mentor or higher.")


async def require_senior_mod(
    current_user: dict[str, Any], session: AsyncSession
) -> None:
    uid = int(current_user["sub"])
    roles = await get_effective_roles(uid, session)
    if not await check_page_permission("staff.badges", "delete", roles, session):
        raise HTTPException(403, "Requires Senior Moderator or higher.")
