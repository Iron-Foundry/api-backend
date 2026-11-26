"""The OSRSClans loot rate and drop source queries.

OSRSClans copies the OSRS Wiki drop tables once a day. `client.cached_page`
fetches and caches each query.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from valkey.asyncio import Valkey

from app.services.osrsclans.client import cached_page
from app.services.osrsclans.loot_rate_models import (
    LootCategory,
    LootRatePage,
    LootSourcePage,
)


@dataclass(frozen=True)
class LootRateAsk:
    """The filters and window of one `/loot-rates` query."""

    path: ClassVar[str] = "/loot-rates"

    item: int | None = None
    source: str | None = None
    page: str | None = None
    category: LootCategory | None = None
    wom_metric: str | None = None
    q: str | None = None
    level: int | None = None
    points: int | None = None
    raid_level: int | None = None
    limit: int = 50
    offset: int = 0
    collection_log: bool | None = None


@dataclass(frozen=True)
class LootSourceAsk:
    """The filters and window of one `/loot-rates/sources` query."""

    path: ClassVar[str] = "/loot-rates/sources"

    page: str | None = None
    category: LootCategory | None = None
    wom_metric: str | None = None
    q: str | None = None
    limit: int = 50
    offset: int = 0
    collection_log: bool | None = None


async def cached_loot_rates(valkey: Valkey, ask: LootRateAsk) -> LootRatePage:
    """Return one window of loot rates, from the cache when a copy is current."""
    return await cached_page(valkey, ask, LootRatePage)


async def cached_loot_sources(valkey: Valkey, ask: LootSourceAsk) -> LootSourcePage:
    """Return one window of drop sources, from the cache when a copy is current."""
    return await cached_page(valkey, ask, LootSourcePage)
