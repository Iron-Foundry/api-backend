from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TileRepositoryTile
from app.dependencies import get_current_user, get_session
from app.services.page_permissions import require_page_permission

from ._serializers import _serialize_tile
from .schemas import TileBody, TilePatch

router = APIRouter()
_PERM = Depends(require_page_permission("staff.tile-repository", "edit"))


@router.get("/repository")
async def list_tiles(
    q: str = Query("", min_length=0),
    tag: str = Query("", min_length=0),
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
) -> list[dict[str, Any]]:
    """Search the reusable tile repository by text or tag."""
    rows = (
        (
            await session.execute(
                select(TileRepositoryTile).order_by(TileRepositoryTile.title)
            )
        )
        .scalars()
        .all()
    )
    results = []
    for t in rows:
        if q and q.lower() not in t.title.lower():
            continue
        if tag and tag not in (t.tags or []):
            continue
        results.append(_serialize_tile(t))
    return results


@router.post("/repository", status_code=201)
async def create_tile(
    body: TileBody,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Add a tile to the repository for future events to draw on."""
    now = datetime.now(UTC)
    tile = TileRepositoryTile(
        title=body.title,
        description=body.description,
        icon_url=body.icon_url,
        icon_source=body.icon_source,
        items=body.items,
        requirement=body.requirement.model_dump() if body.requirement else None,
        tags=body.tags,
        created_by=int(current_user["sub"]),
        created_at=now,
        updated_at=now,
    )
    session.add(tile)
    await session.commit()
    return {"id": str(tile.id)}


@router.get("/repository/{tile_id}")
async def get_tile(
    tile_id: int,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
) -> dict[str, Any]:
    """Return one repository tile with its requirements and modifiers."""
    tile = (
        await session.execute(
            select(TileRepositoryTile).where(TileRepositoryTile.id == tile_id)
        )
    ).scalar_one_or_none()
    if tile is None:
        raise HTTPException(404, "Tile not found.")
    return _serialize_tile(tile)


@router.patch("/repository/{tile_id}")
async def patch_tile(
    tile_id: int,
    body: TilePatch,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
) -> dict[str, Any]:
    """Update a repository tile's text, requirements, or modifiers."""
    tile = (
        await session.execute(
            select(TileRepositoryTile).where(TileRepositoryTile.id == tile_id)
        )
    ).scalar_one_or_none()
    if tile is None:
        raise HTTPException(404, "Tile not found.")
    if body.title is not None:
        tile.title = body.title
    if body.description is not None:
        tile.description = body.description
    if body.icon_url is not None:
        tile.icon_url = body.icon_url
    if body.icon_source is not None:
        tile.icon_source = body.icon_source
    if body.items is not None:
        tile.items = body.items
    if "requirement" in body.model_fields_set:
        tile.requirement = body.requirement.model_dump() if body.requirement else None
    if body.tags is not None:
        tile.tags = body.tags
    tile.updated_at = datetime.now(UTC)
    await session.commit()
    return {"ok": True}


@router.delete("/repository/{tile_id}")
async def delete_tile(
    tile_id: int,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
) -> dict[str, Any]:
    """Delete a repository tile. Boards already built from it are unaffected."""
    tile = (
        await session.execute(
            select(TileRepositoryTile).where(TileRepositoryTile.id == tile_id)
        )
    ).scalar_one_or_none()
    if tile is None:
        raise HTTPException(404, "Tile not found.")
    await session.delete(tile)
    await session.commit()
    return {"ok": True}
