from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import APIRouter, Query
from loguru import logger

from app.services.http.wiki import OsrsWikiContentHandler

router = APIRouter()

_OSRS_CACHE_SERVICE_URL = os.getenv(
    "OSRS_CACHE_SERVICE_URL", "http://osrs-cache-service:8100"
).rstrip("/")

_CANDIDATE_LIMIT = 200
_RESULT_LIMIT = 10


@router.get("/osrs/npcs")
async def search_osrs_npcs(q: str = Query("", min_length=0)) -> list[dict[str, Any]]:
    """Search OSRS NPC names for the tile editor. Needs at least two characters.

    Names and ids come from our own cache; the wiki supplies only the artwork,
    which the cache cannot render. An NPC with no wiki image still comes back,
    with `icon_url` empty.
    """
    if not q or len(q) < 2:
        return []
    matches = await _search_cache(q)
    if not matches:
        return []
    icons = await _wiki_icons([name for _, name in matches])
    return [
        {"id": npc_id, "name": name, "icon_url": icons.get(name, "")}
        for npc_id, name in matches
    ]


async def _search_cache(term: str) -> list[tuple[int, str]]:
    """The best id per distinct name: the highest combat level, else the lowest id.

    One name spans many ids - Vorkath alone is five - because a definition is
    also written for each form a varbit transforms into. The fightable form is
    the one carrying a combat level.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{_OSRS_CACHE_SERVICE_URL}/npcs",
                params={"search": term, "limit": _CANDIDATE_LIMIT},
            )
            resp.raise_for_status()
            rows = resp.json()
    except Exception as exc:
        logger.warning("OSRS NPC search: cache service unavailable: {}", exc)
        return []

    best: dict[str, tuple[int, int]] = {}
    for row in rows:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        level = row.get("combat_level") or 0
        npc_id = row["npc_id"]
        current = best.get(name)
        if current is None or level > current[1]:
            best[name] = (npc_id, level)

    lowered = term.lower()
    ranked = sorted(best, key=lambda name: (not name.lower().startswith(lowered), name))
    return [(best[name][0], name) for name in ranked[:_RESULT_LIMIT]]


async def _wiki_icons(names: list[str]) -> dict[str, str]:
    try:
        async with OsrsWikiContentHandler(timeout=10.0) as wiki:
            return await wiki.get_page_thumbnails(names)
    except Exception as exc:
        logger.warning("OSRS NPC search: wiki artwork lookup failed: {}", exc)
        return {}
