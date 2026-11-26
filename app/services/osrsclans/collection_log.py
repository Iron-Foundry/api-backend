"""The drops of one collection log page, gathered from every source that fills it.

OSRSClans has no filter on the collection log page. This reads all flagged
sources, keeps those that fill the page, then reads each kept source's flagged
rows. Each query goes through `cached_page`, so a repeat costs no request.
"""

from __future__ import annotations

import asyncio
import re

from pydantic import BaseModel
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
_APOSTROPHES = str.maketrans("", "", "'`" + chr(0x2018) + chr(0x2019))
_NOT_WORD = re.compile(r"[^0-9a-z]+")


class CollectionLogPage(BaseModel):
    """One collection log page and the count of drop sources that fill it."""

    name: str
    sources: int


def page_key(name: str) -> str:
    """Return a name without case, apostrophes or punctuation, its words one space apart."""
    folded = name.casefold().translate(_APOSTROPHES)
    return " ".join(_NOT_WORD.sub(" ", folded).split())


def _page_rank(name: str, key: str) -> tuple[int, str]:
    own = page_key(name)
    if own == key:
        return (0, name)
    return (1 if own.startswith(key) else 2, name)


def matching_pages(
    sources: list[LootSource], q: str, limit: int
) -> list[CollectionLogPage]:
    """Return the pages whose key holds the key of `q`, exact and prefix matches first."""
    key = page_key(q)
    counts: dict[str, int] = {}
    for source in sources:
        if source.collection_log_page:
            name = source.collection_log_page
            counts[name] = counts.get(name, 0) + 1
    hits = sorted(
        (name for name in counts if key in page_key(name)),
        key=lambda name: _page_rank(name, key),
    )
    return [CollectionLogPage(name=n, sources=counts[n]) for n in hits[:limit]]


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
    return name is not None and page_key(name) == page_key(page_name)


async def cached_collection_log_pages(
    valkey: Valkey, q: str, limit: int
) -> list[CollectionLogPage]:
    """Return the collection log pages whose name holds `q`, ignoring case and apostrophes."""
    return matching_pages(await _flagged_sources(valkey), q, limit)


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
