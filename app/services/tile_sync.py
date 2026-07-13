"""Coordinates OSRS map tile syncing across gunicorn workers via Valkey.

A Valkey lock ensures exactly one worker runs a sync; status, progress, and stop
requests are shared through Valkey so they work from any worker.
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import MapTile
from app.services import tile_sync_state as sync_state
from app.services.tile_crawler import TileCrawler

if TYPE_CHECKING:
    from valkey.asyncio import Valkey

    from app.services.tile_events import TileEventBus


class TileSyncService:
    """Owns the sync task lifecycle and cross-worker coordination."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None,
        *,
        max_zoom: int = 9,
        concurrency: int = 8,
        delay_ms: int = 100,
        event_bus: TileEventBus | None = None,
        valkey: Valkey | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._max_zoom = max_zoom
        self._concurrency = concurrency
        self._delay_ms = delay_ms
        self._event_bus = event_bus
        self._valkey = valkey
        self._owner = str(os.getpid())
        self._task: asyncio.Task[None] | None = None
        self._crawler: TileCrawler | None = None
        self._should_stop = False

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def _progress(self) -> dict:
        return self._crawler.progress() if self._crawler else {"running": True}

    async def status(self) -> dict:
        if self._valkey is not None:
            return await sync_state.read_state(self._valkey)
        return self._progress() if self.is_running else {"running": False}

    async def cached_count(self) -> int:
        if not self._session_factory:
            return 0
        async with self._session_factory() as session:
            result = await session.execute(select(func.count()).select_from(MapTile))
            return result.scalar() or 0

    async def cached_bytes(self) -> int:
        if not self._session_factory:
            return 0
        async with self._session_factory() as session:
            result = await session.execute(
                select(func.coalesce(func.sum(MapTile.size_bytes), 0))
            )
            return result.scalar() or 0

    async def start(self, *, force: bool = False) -> dict:
        if self._valkey is not None:
            if not await sync_state.acquire_lock(self._valkey, self._owner):
                return {"started": False, "reason": "already running"}
        elif self.is_running:
            return {"started": False, "reason": "already running"}
        self._should_stop = False
        self._crawler = TileCrawler(
            self._session_factory,
            max_zoom=self._max_zoom,
            concurrency=self._concurrency,
            delay_ms=self._delay_ms,
            force=force,
        )
        self._task = asyncio.create_task(self._run(), name="tile-sync")
        logger.info("TileSyncService started (force={})", force)
        return {"started": True, "force": force}

    async def stop(self) -> dict:
        running = False
        if self._valkey is not None:
            running = (await sync_state.read_state(self._valkey)).get("running", False)
            await sync_state.request_stop(self._valkey)
        if self._task and not self._task.done():
            running = True
            self._should_stop = True
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("TileSyncService stop requested")
        return {"stopped": bool(running)}

    async def _emit(self, event_type: str) -> None:
        if self._event_bus is not None:
            await self._event_bus.publish(event_type, **self._progress())

    async def _write_state(self) -> None:
        if self._valkey is not None:
            await sync_state.write_state(self._valkey, self._progress())

    async def _check_stop(self) -> bool:
        if self._should_stop:
            return True
        if self._valkey is not None:
            return await sync_state.stop_requested(self._valkey)
        return False

    async def _on_progress(self) -> None:
        await self._emit("sync_progress")
        await self._write_state()

    async def _run(self) -> None:
        if self._crawler is None:
            return
        await self._emit("sync_started")
        await self._write_state()
        stopped = False
        try:
            stopped = await self._crawler.run(self._check_stop, self._on_progress)
        except asyncio.CancelledError:
            stopped = True
        finally:
            if self._valkey is not None:
                await sync_state.release_lock(self._valkey)
            await self._emit("sync_stopped" if stopped else "sync_complete")
            logger.info("TileSyncService {}", "stopped" if stopped else "complete")
