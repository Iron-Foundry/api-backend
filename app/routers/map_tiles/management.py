"""Tile cache management: delete all, delete by region, coverage query."""

from __future__ import annotations

import math
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import CursorResult, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MapTile
from app.dependencies import get_session
from app.services.page_permissions import require_page_permission

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]
RegionPath = Annotated[int, Path(ge=0, le=65535)]

_MAP_WIDTH = 104448
_MAP_HEIGHT = 364544
_EXPLV_ZOOM_MAX = 11


def _tile_cols(z: int) -> int:
    return math.ceil(_MAP_WIDTH / 256 / (2 ** (_EXPLV_ZOOM_MAX - z)))


def _tile_rows(z: int) -> int:
    return math.ceil(_MAP_HEIGHT / 256 / (2 ** (_EXPLV_ZOOM_MAX - z)))


@router.delete(
    "/",
    dependencies=[Depends(require_page_permission("staff.map_tiles", "delete"))],
)
async def delete_all_tiles(session: SessionDep) -> dict:
    """Wipe the entire tile cache. Use before a forced resync after an OSRS map update."""
    await session.execute(delete(MapTile))
    await session.commit()
    return {"deleted": True}


@router.delete(
    "/region/{region_id}",
    dependencies=[Depends(require_page_permission("staff.map_tiles", "delete"))],
)
async def delete_region_tiles(region_id: RegionPath, session: SessionDep) -> dict:
    """Delete cached tiles for a specific OSRS region ID.

    Tiles are re-fetched lazily from upstream on next access.
    Region IDs: ((osrs_x // 64) << 8) | (osrs_y // 64).
    """
    result = await session.execute(
        delete(MapTile).where(MapTile.region_id == region_id)
    )
    await session.commit()
    return {"deleted": cast(CursorResult, result).rowcount}


@router.get(
    "/coverage",
    dependencies=[Depends(require_page_permission("staff.map_tiles", "read"))],
)
async def tile_coverage(
    session: SessionDep,
    plane: Annotated[int, Query(ge=0, le=3)] = 0,
    z: Annotated[int, Query(ge=4, le=11)] = 8,
) -> dict:
    """Return the set of cached tile coordinates at the given zoom level.

    Response tiles: list of [x, y, has_content_int] for all rows cached at (plane, z).
    """
    rows = await session.execute(
        select(MapTile.x, MapTile.y, MapTile.has_content).where(
            MapTile.plane == plane,
            MapTile.z == z,
        )
    )
    tiles = [[r.x, r.y, int(r.has_content)] for r in rows]
    return {
        "plane": plane,
        "z": z,
        "cols": _tile_cols(z),
        "rows": _tile_rows(z),
        "tiles": tiles,
    }
