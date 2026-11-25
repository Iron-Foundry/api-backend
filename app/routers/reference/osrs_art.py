from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from valkey.asyncio import Valkey

from app.dependencies import get_valkey
from app.docs import responses
from app.services.osrsclans.art import (
    NpcSearchAsk,
    OsrsNpcPage,
    OsrsSpritePage,
    SpriteSearchAsk,
    cached_npcs,
    cached_sprites,
)
from app.services.osrsclans.client import OsrsClansError

router = APIRouter(prefix="/osrs", responses=responses.PROXIED)

ValkeyDep = Annotated[Valkey, Depends(get_valkey)]
NameQuery = Annotated[str, Query(min_length=2, max_length=64)]
LimitQuery = Annotated[int, Query(ge=1, le=50)]
OffsetQuery = Annotated[int, Query(ge=0)]


@router.get("/npcs")
async def search_npcs(
    valkey: ValkeyDep, q: NameQuery, limit: LimitQuery = 20, offset: OffsetQuery = 0
) -> OsrsNpcPage:
    """Return the NPCs from OSRSClans whose name holds `q`, with each one's still."""
    try:
        return await cached_npcs(valkey, NpcSearchAsk(q, limit, offset))
    except OsrsClansError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/sprites")
async def search_sprites(
    valkey: ValkeyDep, q: NameQuery, limit: LimitQuery = 20, offset: OffsetQuery = 0
) -> OsrsSpritePage:
    """Return the interface sprites from OSRSClans whose name holds `q`."""
    try:
        return await cached_sprites(valkey, SpriteSearchAsk(q, limit, offset))
    except OsrsClansError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
