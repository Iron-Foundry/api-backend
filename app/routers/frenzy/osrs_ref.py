from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from loguru import logger
from valkey.asyncio import Valkey

from app.dependencies import get_valkey

from ._constants import _ACTIVITIES_KEY, _BOSSES_KEY, _ITEMS_KEY
from ._osrs_cache import _refresh_osrs_activities, _refresh_osrs_bosses, _refresh_osrs_items

router = APIRouter()


@router.get("/osrs/items")
async def search_osrs_items(
    q: str = Query("", min_length=0),
    valkey: Valkey = Depends(get_valkey),
) -> list[dict]:
    if not q or len(q) < 2:
        return []
    raw = await valkey.get(_ITEMS_KEY)
    if not raw:
        try:
            await _refresh_osrs_items(valkey)
            raw = await valkey.get(_ITEMS_KEY)
        except Exception as exc:
            logger.warning("osrs items refresh failed: {}", exc)
            return []
    if not raw:
        return []
    norm_q = q.lower().replace("'", "").strip()
    all_items: list[dict] = json.loads(raw)
    return [item for item in all_items if norm_q in item["name"].lower().replace("'", "")][:30]


@router.get("/osrs/bosses")
async def get_osrs_bosses(valkey: Valkey = Depends(get_valkey)) -> list[dict]:
    raw = await valkey.get(_BOSSES_KEY)
    if not raw:
        await _refresh_osrs_bosses(valkey)
        raw = await valkey.get(_BOSSES_KEY)
    return json.loads(raw) if raw else []


@router.get("/osrs/activities")
async def get_osrs_activities(valkey: Valkey = Depends(get_valkey)) -> list[dict]:
    raw = await valkey.get(_ACTIVITIES_KEY)
    if not raw:
        await _refresh_osrs_activities(valkey)
        raw = await valkey.get(_ACTIVITIES_KEY)
    return json.loads(raw) if raw else []
