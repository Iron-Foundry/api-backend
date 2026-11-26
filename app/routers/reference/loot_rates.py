from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

from app.dependencies import get_session, get_valkey
from app.docs import responses
from app.services.osrsclans.client import OsrsClansError
from app.services.osrsclans.foundry_rates import fill_rate_page, fill_source_page
from app.services.osrsclans.loot_rate_models import (
    LootCategory,
    LootRatePage,
    LootSourcePage,
)
from app.services.osrsclans.loot_rates import (
    LootRateAsk,
    LootSourceAsk,
    cached_loot_rates,
    cached_loot_sources,
)

router = APIRouter(prefix="/loot-rates", responses=responses.PROXIED)

ValkeyDep = Annotated[Valkey, Depends(get_valkey)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
PageQuery = Annotated[str | None, Query(min_length=1, max_length=200)]
CategoryQuery = Annotated[LootCategory | None, Query()]
WomMetricQuery = Annotated[str | None, Query(min_length=1, max_length=64)]
TextQuery = Annotated[str | None, Query(min_length=2, max_length=64)]
LimitQuery = Annotated[int, Query(ge=1, le=500)]
OffsetQuery = Annotated[int, Query(ge=0)]


@router.get("")
async def list_loot_rates(
    valkey: ValkeyDep,
    session: SessionDep,
    item: Annotated[int | None, Query(ge=0)] = None,
    source: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    page: PageQuery = None,
    category: CategoryQuery = None,
    wom_metric: WomMetricQuery = None,
    q: TextQuery = None,
    level: Annotated[int | None, Query(ge=1, le=99)] = None,
    points: Annotated[int | None, Query(ge=0, le=3_420_000)] = None,
    raid_level: Annotated[int | None, Query(ge=0, le=600)] = None,
    limit: LimitQuery = 50,
    offset: OffsetQuery = 0,
) -> LootRatePage:
    """Return loot rates from OSRSClans: each item's chance from each drop source.

    `item`, `source`, `page`, `category` and `wom_metric` keep one of each. `q`
    keeps the rows whose item or source name holds the text. `level` sets the
    level that a skilling pet or clue nest chance is computed at. `points` and
    `raid_level` set the raid that `chance_per_raid` is computed at. A row with
    no OSRSClans kill rate takes the staff-set rate of its source, marked
    `foundry`.
    """
    ask = LootRateAsk(
        item,
        source,
        page,
        category,
        wom_metric,
        q,
        level,
        points,
        raid_level,
        limit,
        offset,
    )
    try:
        rates = await cached_loot_rates(valkey, ask)
    except OsrsClansError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return await fill_rate_page(session, rates)


@router.get("/sources")
async def list_loot_sources(
    valkey: ValkeyDep,
    session: SessionDep,
    page: PageQuery = None,
    category: CategoryQuery = None,
    wom_metric: WomMetricQuery = None,
    q: TextQuery = None,
    limit: LimitQuery = 50,
    offset: OffsetQuery = 0,
) -> LootSourcePage:
    """Return the drop sources from OSRSClans, with each source's kill rate.

    `page`, `category` and `wom_metric` keep one of each. `q` keeps the sources
    whose name, or the name of an item they drop, holds the text. A source with
    no OSRSClans kill rate takes its staff-set rate, marked `foundry`.
    """
    ask = LootSourceAsk(page, category, wom_metric, q, limit, offset)
    try:
        sources = await cached_loot_sources(valkey, ask)
    except OsrsClansError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return await fill_source_page(session, sources)
