"""The drops of one collection log page, gathered from every source that fills it.

OSRSClans has no filter on the collection log page. This reads all flagged
sources, keeps those that fill the page, then reads each kept source's flagged
rows. Each query goes through `cached_page`, so a repeat costs no request.
"""

from __future__ import annotations

import asyncio

from valkey.asyncio import Valkey

from app.services.osrsclans.loot_rate_models import LootRate, LootRatePage, LootSource
from app.services.osrsclans.loot_rates import (
    LootRateAsk,
    LootSourceAsk,
    cached_loot_rates,
    cached_loot_sources,
)

_SOURCE_WINDOW = 500
_ROW_WINDOW = 100


async def _flagged_sources(valkey: Valkey) -> list[LootSource]:
    sources: list[LootSource] = []
    offset = 0
    while True:
        ask = LootSourceAsk(limit=_SOURCE_WINDOW, offset=offset, collection_log=True)
        page = await cached_loot_sources(valkey, ask)
        sources.extend(page.items)
        offset += _SOURCE_WINDOW
        if not page.items or offset >= page.total:
            return sources


def _on_page(name: str | None, page_name: str) -> bool:
    return name is not None and name.casefold() == page_name.casefold()


async def cached_collection_log(valkey: Valkey, page_name: str) -> LootRatePage:
    """Return the flagged rows of all sources that fill the named collection log page."""
    kept = [
        s.source
        for s in await _flagged_sources(valkey)
        if _on_page(s.collection_log_page, page_name)
    ]
    pages = await asyncio.gather(
        *(
            cached_loot_rates(
                valkey,
                LootRateAsk(source=source, limit=_ROW_WINDOW, collection_log=True),
            )
            for source in kept
        )
    )
    rows: list[LootRate] = [
        row
        for page in pages
        for row in page.items
        if _on_page(row.collection_log_page, page_name)
    ]
    return LootRatePage(items=rows, total=len(rows), limit=len(rows), offset=0)
