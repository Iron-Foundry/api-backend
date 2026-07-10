"""Tile proxy endpoint: serve cached tiles, lazy-fetching from upstream on miss."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Request
from fastapi.responses import Response
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MapTile
from app.dependencies import get_session
from app.services.tile_processor import process_tile, tile_region_id

router = APIRouter()

_UPSTREAM = "https://raw.githubusercontent.com/Explv/osrs_map_tiles/master"
_CACHE_FOREVER = "public, max-age=31536000, immutable"

SessionDep = Annotated[AsyncSession, Depends(get_session)]
PlanePath = Annotated[int, Path(ge=0, le=3)]
ZoomPath = Annotated[int, Path(ge=4, le=11)]
CoordPath = Annotated[int, Path(ge=0)]


@router.get("/{plane}/{z}/{x}/{y}")
async def serve_tile(
    request: Request,
    plane: PlanePath,
    z: ZoomPath,
    x: CoordPath,
    y: CoordPath,
    session: SessionDep,
) -> Response:
    """Serve a cached map tile, fetching and caching from upstream on first access."""
    tile = await session.get(MapTile, (plane, z, x, y))
    if tile:
        return Response(
            content=tile.data,
            media_type=tile.content_type,
            headers={
                "Cache-Control": _CACHE_FOREVER,
                "X-Tile-Color": tile.dominant_color or "",
                "X-Tile-Has-Content": str(tile.has_content).lower(),
            },
        )

    raw = await _fetch_upstream(plane, z, x, y)
    if raw is None:
        raise HTTPException(404, "Tile not found")

    processed = await asyncio.to_thread(process_tile, raw)
    region = tile_region_id(x, y, z)
    await session.execute(
        pg_insert(MapTile)
        .values(
            plane=plane,
            z=z,
            x=x,
            y=y,
            data=processed.data,
            content_type=processed.content_type,
            size_bytes=processed.size_bytes,
            dominant_color=processed.dominant_color,
            has_content=processed.has_content,
            region_id=region,
            fetched_at=datetime.now(timezone.utc),
        )
        .on_conflict_do_nothing()
    )
    await session.commit()

    bus = getattr(request.app.state, "tile_event_bus", None)
    if bus is not None:
        await bus.publish("tile_fetched", plane=plane, z=z, x=x, y=y, source="lazy")

    return Response(
        content=processed.data,
        media_type=processed.content_type,
        headers={
            "Cache-Control": _CACHE_FOREVER,
            "X-Tile-Color": processed.dominant_color or "",
            "X-Tile-Has-Content": str(processed.has_content).lower(),
        },
    )


async def _fetch_upstream(plane: int, z: int, x: int, y: int) -> bytes | None:
    url = f"{_UPSTREAM}/{plane}/{z}/{x}/{y}.png"
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(url)
        except httpx.RequestError:
            return None
    return resp.content if resp.status_code == 200 else None
