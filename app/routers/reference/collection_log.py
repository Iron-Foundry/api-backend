from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

from app.dependencies import get_session, get_valkey
from app.docs import responses
from app.services.osrsclans.client import OsrsClansError
from app.services.osrsclans.collection_log import (
    CollectionLogPage,
    cached_collection_log,
    cached_collection_log_pages,
)
from app.services.osrsclans.foundry_rates import fill_rate_page
from app.services.osrsclans.loot_rate_models import LootRatePage

router = APIRouter(prefix="/loot-rates/collection-log", responses=responses.PROXIED)

ValkeyDep = Annotated[Valkey, Depends(get_valkey)]
NameQuery = Annotated[str, Query(min_length=2, max_length=64)]


@router.get("")
async def list_collection_log_rates(
    valkey: ValkeyDep,
    session: Annotated[AsyncSession, Depends(get_session)],
    name: NameQuery,
) -> LootRatePage:
    """Return the drops of one collection log page, from every source that fills it.

    `name` matches the page name without regard to case, apostrophes or
    punctuation. An item that several sources drop has one row per source. A row
    with no OSRSClans kill rate takes the staff-set rate of its source, marked
    `foundry`.
    """
    try:
        rates = await cached_collection_log(valkey, name)
    except OsrsClansError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return await fill_rate_page(session, rates)


@router.get("/pages")
async def search_collection_log_pages(
    valkey: ValkeyDep,
    q: NameQuery,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[CollectionLogPage]:
    """Return the collection log pages whose name holds `q`.

    The match ignores case, apostrophes and punctuation, so "kril" finds
    "K'ril Tsutsaroth". An exact match comes first, then the names that start
    with `q`. Each page carries the count of drop sources that fill it.
    """
    try:
        return await cached_collection_log_pages(valkey, q, limit)
    except OsrsClansError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
