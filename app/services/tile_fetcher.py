"""Download and cache individual OSRS map tiles from Explv's GitHub repository."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx
from loguru import logger
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import MapTile
from app.services.tile_processor import process_tile, tile_region_id

_UPSTREAM = "https://raw.githubusercontent.com/Explv/osrs_map_tiles/master"


async def tile_exists(
    session_factory: async_sessionmaker[AsyncSession],
    plane: int,
    z: int,
    tx: int,
    ty: int,
) -> bool:
    async with session_factory() as session:
        return await session.get(MapTile, (plane, z, tx, ty)) is not None


async def download_tile(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    plane: int,
    z: int,
    tx: int,
    ty: int,
) -> bytes | None:
    url = f"{_UPSTREAM}/{plane}/{z}/{tx}/{ty}.png"
    for attempt in range(5):
        async with sem:
            try:
                resp = await client.get(url)
            except httpx.RequestError as exc:
                logger.warning("tile request error {}: {}", url, exc)
                return None
        if resp.status_code == 404:
            return None
        if resp.status_code in (429, 403):
            delay = 60 * (2**attempt)
            logger.warning("rate limited ({}), waiting {}s", resp.status_code, delay)
            await asyncio.sleep(delay)
            continue
        if resp.status_code == 200:
            return resp.content
        logger.warning("unexpected {} for {}", resp.status_code, url)
        return None
    logger.error("max retries exceeded for {}", url)
    return None


async def cache_tile(
    session_factory: async_sessionmaker[AsyncSession],
    plane: int,
    z: int,
    tx: int,
    ty: int,
    raw: bytes,
    *,
    force: bool = False,
) -> None:
    processed = await asyncio.to_thread(process_tile, raw)
    region = tile_region_id(tx, ty, z)
    values: dict = {
        "plane": plane,
        "z": z,
        "x": tx,
        "y": ty,
        "data": processed.data,
        "content_type": processed.content_type,
        "size_bytes": processed.size_bytes,
        "dominant_color": processed.dominant_color,
        "has_content": processed.has_content,
        "region_id": region,
        "fetched_at": datetime.now(timezone.utc),
    }
    stmt = pg_insert(MapTile).values(**values)
    if force:
        update_cols = {
            k: v for k, v in values.items() if k not in ("plane", "z", "x", "y")
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=["plane", "z", "x", "y"], set_=update_cols
        )
    else:
        stmt = stmt.on_conflict_do_nothing()
    async with session_factory() as session:
        await session.execute(stmt)
        await session.commit()
