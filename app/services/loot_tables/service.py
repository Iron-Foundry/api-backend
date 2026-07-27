"""Daily background service that ingests wiki drop tables into reference tables."""

from __future__ import annotations

import asyncio
import contextlib

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.http import OsrsWikiContentHandler

from ._catalog import load_catalog
from ._drops import parse_drop_tables
from ._items import fetch_item_index
from ._repository import prune_sources, store_source_drops

POLL_INTERVAL = 86400
_FETCH_DELAY = 0.5


class LootTablesService:
    """Refreshes loot_sources and loot_drops daily from the OSRS Wiki."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession] | None
    ) -> None:
        self._session_factory = session_factory
        self._task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._poll_loop(), name="loot-tables-refresh")
        logger.info("LootTablesService started (poll_interval={}s)", POLL_INTERVAL)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("LootTablesService stopped")

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self._refresh()
            except Exception as exc:
                logger.warning("LootTablesService._refresh error: {}", exc)
            await asyncio.sleep(POLL_INTERVAL)

    async def _refresh(self) -> None:
        if self._session_factory is None:
            logger.warning("LootTablesService: no session_factory - skipping")
            return

        catalog = load_catalog()
        item_index = await fetch_item_index()
        logger.info(
            "LootTablesService: refreshing {} sources (item index: {})",
            len(catalog),
            len(item_index),
        )

        stored = 0
        async with OsrsWikiContentHandler() as wiki:
            for entry in catalog:
                try:
                    wikitext = await wiki.get_page_wikitext(entry.wiki_page)
                    drops = parse_drop_tables(wikitext)
                    async with self._session_factory() as session:
                        await store_source_drops(session, entry, drops, item_index)
                    stored += 1
                except Exception as exc:
                    logger.warning("LootTablesService: {} failed: {}", entry.slug, exc)
                await asyncio.sleep(_FETCH_DELAY)

        async with self._session_factory() as session:
            await prune_sources(session, {entry.slug for entry in catalog})

        logger.info("LootTablesService: refreshed {}/{} sources", stored, len(catalog))


__all__ = ["LootTablesService"]
