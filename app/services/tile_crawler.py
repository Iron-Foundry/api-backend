"""OSRS tile grid crawl: walks zoom levels, fetching and caching each tile."""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Awaitable, Callable

import httpx
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.tile_fetcher import cache_tile, download_tile, tile_exists

_MAP_WIDTH = 104448
_MAP_HEIGHT = 364544
_EXPLV_ZOOM_MIN = 4
_EXPLV_ZOOM_MAX = 11
_STOP_CHECK_INTERVAL = 20
_PROGRESS_INTERVAL = 100


def tile_cols(z: int) -> int:
    return math.ceil(_MAP_WIDTH / 256 / (2 ** (_EXPLV_ZOOM_MAX - z)))


def tile_rows(z: int) -> int:
    return math.ceil(_MAP_HEIGHT / 256 / (2 ** (_EXPLV_ZOOM_MAX - z)))


class TileCrawler:
    """Downloads OSRS tiles across zoom levels while tracking progress counters."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None,
        *,
        max_zoom: int,
        concurrency: int,
        delay_ms: int,
        force: bool,
    ) -> None:
        self._sf = session_factory
        self._max_zoom = max_zoom
        self._concurrency = concurrency
        self._delay_ms = delay_ms
        self._force = force
        self.processed = 0
        self.current_zoom = 0
        self.started_at = 0.0
        self.total = sum(
            tile_cols(z) * tile_rows(z) * 4
            for z in range(_EXPLV_ZOOM_MIN, max_zoom + 1)
        )

    def progress(self) -> dict:
        elapsed = time.monotonic() - self.started_at if self.started_at else 0.0
        rate = self.processed / elapsed if elapsed > 0 else 0.0
        remaining = max(0, self.total - self.processed)
        return {
            "running": True,
            "processed": self.processed,
            "total": self.total,
            "current_zoom": self.current_zoom,
            "rate_per_sec": round(rate, 2),
            "eta_seconds": round(remaining / rate) if rate > 0 else None,
        }

    async def run(
        self,
        should_stop: Callable[[], Awaitable[bool]],
        on_progress: Callable[[], Awaitable[None]],
    ) -> bool:
        """Crawl all zoom levels. Returns True if halted early by should_stop."""
        if not self._sf:
            return False
        self.started_at = time.monotonic()
        self.processed = 0
        sem = asyncio.Semaphore(self._concurrency)
        limits = httpx.Limits(max_connections=self._concurrency)
        async with httpx.AsyncClient(limits=limits, timeout=15.0) as client:
            for z in range(_EXPLV_ZOOM_MIN, self._max_zoom + 1):
                if await self._zoom(client, sem, z, should_stop, on_progress):
                    return True
        return False

    async def _zoom(
        self,
        client: httpx.AsyncClient,
        sem: asyncio.Semaphore,
        z: int,
        should_stop: Callable[[], Awaitable[bool]],
        on_progress: Callable[[], Awaitable[None]],
    ) -> bool:
        self.current_zoom = z
        cols, rows = tile_cols(z), tile_rows(z)
        for plane in range(4):
            for tx in range(cols):
                for ty in range(rows):
                    await self._tile(client, sem, plane, z, tx, ty)
                    await asyncio.sleep(self._delay_ms / 1000)
                    if self.processed % _STOP_CHECK_INTERVAL == 0 and (
                        await should_stop()
                    ):
                        return True
                    if self.processed % _PROGRESS_INTERVAL == 0:
                        await on_progress()
        logger.info("TileCrawler z={} complete", z)
        return False

    async def _tile(
        self,
        client: httpx.AsyncClient,
        sem: asyncio.Semaphore,
        plane: int,
        z: int,
        tx: int,
        ty: int,
    ) -> None:
        if not self._sf:
            return
        if not self._force and await tile_exists(self._sf, plane, z, tx, ty):
            self.processed += 1
            return
        raw = await download_tile(client, sem, plane, z, tx, ty)
        if raw is not None:
            await cache_tile(self._sf, plane, z, tx, ty, raw, force=self._force)
        self.processed += 1
