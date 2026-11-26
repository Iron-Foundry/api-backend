"""Keeps the OSRS name indexes built while the site runs."""

from __future__ import annotations

import asyncio
import contextlib
import time

from loguru import logger
from valkey.asyncio import Valkey

from app.services.osrsclans.client import OsrsClansError
from app.services.osrsclans.cooldown import OsrsClansCoolingDownError
from app.services.osrsclans.name_index import refresh_name_indexes

# Under the hour that `cached_page` keeps an OSRSClans answer, so a search never
# finds its index past the age at which it would rebuild it itself.
REFRESH_SECONDS = 50 * 60
RETRY_SECONDS = 60


class NameIndexService:
    """Builds the item, NPC and sprite name indexes at start, then every 50 minutes.

    A failed build keeps the last indexes for searches and retries after a minute.
    """

    def __init__(self, valkey: Valkey) -> None:
        self._valkey = valkey
        self._task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="osrs-name-indexes")
        logger.info("NameIndexService started (refresh={}s)", REFRESH_SECONDS)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("NameIndexService stopped")

    async def _loop(self) -> None:
        while True:
            built = await self._refresh_once()
            await asyncio.sleep(REFRESH_SECONDS if built else RETRY_SECONDS)

    async def _refresh_once(self) -> bool:
        started = time.monotonic()
        logger.info("NameIndexService: building the OSRS name indexes")
        try:
            sizes = await refresh_name_indexes(self._valkey)
        except (OsrsClansError, OsrsClansCoolingDownError) as exc:
            # Recoverable: searches keep the last indexes, and the next pass retries.
            logger.warning(
                "NameIndexService: build failed ({}); retrying in {}s",
                exc,
                RETRY_SECONDS,
            )
            return False
        logger.info(
            "NameIndexService: built {} in {:.1f}s", sizes, time.monotonic() - started
        )
        return True
