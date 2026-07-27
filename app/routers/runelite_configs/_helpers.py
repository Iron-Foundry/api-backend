from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RuneLiteConfig
from app.services.page_permissions import check_page_permission
from app.services.rank_mappings import get_effective_roles

_PAGE_ID = "staff.runelite_configs"
_TILE_MARKER_FIELDS = ("regionId", "regionX", "regionY")


class RuneLiteConfigBody(BaseModel):
    type: str
    name: str
    description: str = ""
    data: list[object]


def serialize_config(c: RuneLiteConfig) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "type": c.type,
        "name": c.name,
        "description": c.description,
        "data": c.data,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def validate_config_data(config_type: str, data: list[object]) -> None:
    if config_type != "tile_marker":
        return
    if not data:
        raise HTTPException(422, "Tile marker data must be a non-empty list.")
    for item in data:
        if not isinstance(item, dict) or any(
            field not in item for field in _TILE_MARKER_FIELDS
        ):
            raise HTTPException(
                422, "Each tile marker requires regionId, regionX and regionY."
            )


async def require_permission(
    current_user: dict[str, Any], action: str, session: AsyncSession
) -> None:
    uid = int(current_user["sub"])
    roles = await get_effective_roles(uid, session)
    if not await check_page_permission(_PAGE_ID, action, roles, session):
        raise HTTPException(403, f"Requires permission: {_PAGE_ID}/{action}")
