from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from valkey.asyncio import Valkey

from app.dependencies import get_valkey
from app.services.osrsclans.client import OsrsClansError
from app.services.osrsclans.items import (
    ItemSearchAsk,
    OsrsItem,
    cached_items,
    item_image_url,
)

from ._constants import _ACTIVITIES_KEY, _BOSSES_KEY
from ._osrs_cache import _refresh_osrs_activities, _refresh_osrs_bosses

router = APIRouter()

_ITEM_RESULT_LIMIT = 30


def _match_rank(name: str, q: str) -> int:
    folded, term = name.casefold(), q.casefold()
    if folded == term:
        return 0
    return 1 if folded.startswith(term) else 2


def ranked_item_names(items: list[OsrsItem], q: str) -> list[OsrsItem]:
    """Return one item per name, lowest id first, the exact match and prefixes ahead."""
    first: dict[str, OsrsItem] = {}
    for item in sorted(items, key=lambda i: i.id):
        if item.name and item.name.casefold() not in first:
            first[item.name.casefold()] = item
    return sorted(first.values(), key=lambda i: (_match_rank(i.name or "", q), i.name))


@router.get("/osrs/items")
async def search_osrs_items(
    q: str = Query("", min_length=0, max_length=64),
    valkey: Valkey = Depends(get_valkey),
) -> list[dict[str, Any]]:
    """Search OSRS items by name on OSRSClans for the frenzy task editor."""
    if len(q.strip()) < 2:
        return []
    try:
        page = await cached_items(valkey, ItemSearchAsk(q.strip(), _ITEM_RESULT_LIMIT))
    except OsrsClansError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return [
        {
            "id": item.id,
            "name": item.name,
            "icon_url": item_image_url(item.id),
            "members": item.members,
        }
        for item in ranked_item_names(page.items, q.strip())
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
