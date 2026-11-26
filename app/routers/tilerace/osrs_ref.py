from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from valkey.asyncio import Valkey

from app.dependencies import get_valkey
from app.services.osrsclans.art import NpcSearchAsk, OsrsNpc, cached_npcs
from app.services.osrsclans.client import OsrsClansError

router = APIRouter()

_CANDIDATE_LIMIT = 100
_RESULT_LIMIT = 10


@router.get("/osrs/npcs")
async def search_osrs_npcs(
    q: str = Query("", min_length=0, max_length=64),
    valkey: Valkey = Depends(get_valkey),
) -> list[dict[str, Any]]:
    """Search OSRS NPC names on OSRSClans for the tile editor, with each one's still.

    Needs at least two characters.
    """
    term = q.strip()
    if len(term) < 2:
        return []
    try:
        page = await cached_npcs(valkey, NpcSearchAsk(term, _CANDIDATE_LIMIT))
    except OsrsClansError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return [
        {"id": npc.id, "name": npc.name, "icon_url": npc.image_url}
        for npc in fightable_forms(page.items, term)
    ]


def fightable_forms(npcs: list[OsrsNpc], term: str) -> list[OsrsNpc]:
    """The best NPC per distinct name: the highest combat level, else the first id.

    One name spans many ids - Vorkath alone is five - because a definition is
    also written for each form a varbit transforms into. The fightable form is
    the one carrying a combat level. Names that start with `term` rank first.
    """
    best: dict[str, OsrsNpc] = {}
    for npc in npcs:
        name = npc.name.strip()
        current = best.get(name)
        if name and (
            current is None or (npc.combat_level or 0) > (current.combat_level or 0)
        ):
            best[name] = npc
    lowered = term.lower()
    ranked = sorted(best, key=lambda name: (not name.lower().startswith(lowered), name))
    return [best[name] for name in ranked[:_RESULT_LIMIT]]
