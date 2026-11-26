"""Foundry's own kill rates for the OSRSClans drop sources that have none.

A staff member sets a rate per OSRSClans source key in `source_kill_rates`.
A loot rate row or a drop source keeps its OSRSClans rate when it has one.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SourceKillRate
from app.services.osrsclans.loot_rate_models import (
    LootRate,
    LootRatePage,
    LootSource,
    LootSourcePage,
)


async def foundry_rates_for(
    session: AsyncSession, sources: Iterable[str]
) -> dict[str, float]:
    """Return the staff-set kills per hour of the given sources, by source key."""
    keys = set(sources)
    if not keys:
        return {}
    stmt = select(SourceKillRate).where(SourceKillRate.source.in_(keys))
    rows = (await session.execute(stmt)).scalars().all()
    return {row.source: row.kills_per_hour for row in rows}


def with_foundry_rate[Rated: (LootRate, LootSource)](
    entry: Rated, rates: dict[str, float]
) -> Rated:
    """Return the entry with Foundry's rate where OSRSClans gives no kill rate."""
    rate = rates.get(entry.source)
    if entry.kills_per_hour is not None or rate is None:
        return entry
    return entry.model_copy(
        update={"kills_per_hour": rate, "kill_rate_source": "foundry"}
    )


def _rateless_sources(entries: Iterable[LootRate | LootSource]) -> set[str]:
    return {e.source for e in entries if e.kills_per_hour is None}


async def fill_rate_page(session: AsyncSession, page: LootRatePage) -> LootRatePage:
    """Fill each rate-less loot rate row of the page from Foundry's rates."""
    rates = await foundry_rates_for(session, _rateless_sources(page.items))
    items = [with_foundry_rate(row, rates) for row in page.items]
    return page.model_copy(update={"items": items})


async def fill_source_page(
    session: AsyncSession, page: LootSourcePage
) -> LootSourcePage:
    """Fill each rate-less drop source of the page from Foundry's rates."""
    rates = await foundry_rates_for(session, _rateless_sources(page.items))
    items = [with_foundry_rate(source, rates) for source in page.items]
    return page.model_copy(update={"items": items})
