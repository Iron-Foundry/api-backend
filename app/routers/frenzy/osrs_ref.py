from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from valkey.asyncio import Valkey

from app.dependencies import get_valkey
from app.services.osrsclans.client import OsrsClansError
from app.services.osrsclans.items import item_image_url
from app.services.osrsclans.name_index import item_index
from app.services.osrsclans.name_search import best_matches

from ._constants import _ACTIVITIES_KEY, _BOSSES_KEY
from ._osrs_cache import _refresh_osrs_activities, _refresh_osrs_bosses

router = APIRouter()

_ITEM_RESULT_LIMIT = 30


@router.get("/osrs/items")
async def search_osrs_items(
    q: str = Query("", min_length=0, max_length=64),
    valkey: Valkey = Depends(get_valkey),
) -> list[dict[str, Any]]:
    """Search OSRS item names for the frenzy and tile editors, best match first.

    One item per name, the lowest id. The match ignores case, accents and
    punctuation. Foundry matches against OSRSClans' item name list, which it
    reads once an hour.
    """
    if len(q.strip()) < 2:
        return []
    try:
        entries = await item_index(valkey)
    except OsrsClansError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    hits = best_matches(entries, q, _ITEM_RESULT_LIMIT, unique_names=True)
    return [
        {"id": e.id, "name": e.name, "icon_url": item_image_url(e.id)} for e in hits
    ]


@router.get("/osrs/bosses")
async def get_osrs_bosses(valkey: Valkey = Depends(get_valkey)) -> list[dict[str, Any]]:
    """List the boss metrics a frenzy task can target. Cached in Valkey."""
    raw = await valkey.get(_BOSSES_KEY)
    if not raw:
        await _refresh_osrs_bosses(valkey)
        raw = await valkey.get(_BOSSES_KEY)
    return json.loads(raw) if raw else []


@router.get("/osrs/activities")
async def get_osrs_activities(
    valkey: Valkey = Depends(get_valkey),
) -> list[dict[str, Any]]:
    """List the activity metrics a frenzy task can target. Cached in Valkey."""
    raw = await valkey.get(_ACTIVITIES_KEY)
    if not raw:
        await _refresh_osrs_activities(valkey)
        raw = await valkey.get(_ACTIVITIES_KEY)
    return json.loads(raw) if raw else []
