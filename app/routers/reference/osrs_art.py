from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from valkey.asyncio import Valkey

from app.dependencies import get_valkey
from app.docs import responses
from app.services.osrsclans.art import OsrsNpc, OsrsNpcPage, OsrsSpritePage
from app.services.osrsclans.client import OsrsClansError
from app.services.osrsclans.name_index import npc_index, sprite_index
from app.services.osrsclans.name_search import best_matches

router = APIRouter(prefix="/osrs", responses=responses.PROXIED)

ValkeyDep = Annotated[Valkey, Depends(get_valkey)]
NameQuery = Annotated[str, Query(min_length=2, max_length=64)]
LimitQuery = Annotated[int, Query(ge=1, le=50)]
OffsetQuery = Annotated[int, Query(ge=0)]


@router.get("/npcs")
async def search_npcs(
    valkey: ValkeyDep, q: NameQuery, limit: LimitQuery = 20, offset: OffsetQuery = 0
) -> OsrsNpcPage:
    """Return the NPCs whose name holds `q`, best match first, with each one's still.

    The match ignores case, accents and punctuation, so "kril" finds
    "K'ril Tsutsaroth". Foundry matches against OSRSClans' NPC name list, which it
    reads once an hour.
    """
    try:
        hits = best_matches(await npc_index(valkey), q)
    except OsrsClansError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    window = hits[offset : offset + limit]
    items = [OsrsNpc(id=e.id, name=e.name) for e in window]
    return OsrsNpcPage(items=items, total=len(hits), limit=limit, offset=offset)


@router.get("/sprites")
async def search_sprites(
    valkey: ValkeyDep, q: NameQuery, limit: LimitQuery = 20, offset: OffsetQuery = 0
) -> OsrsSpritePage:
    """Return the interface sprites whose name holds `q`, best match first.

    The match ignores case, accents and punctuation. Foundry matches against
    OSRSClans' sprite list, which it reads once an hour.
    """
    try:
        index = await sprite_index(valkey)
    except OsrsClansError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    hits = best_matches(index.entries, q)
    window = [index.sprites[e.id] for e in hits[offset : offset + limit]]
    return OsrsSpritePage(items=window, total=len(hits), limit=limit, offset=offset)
