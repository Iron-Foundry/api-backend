from __future__ import annotations

import re
from typing import Any

import httpx
from fastapi import APIRouter, Query
from loguru import logger

router = APIRouter()

_WIKI_API = "https://oldschool.runescape.wiki/api.php"
_WIKI_IMAGES = "https://oldschool.runescape.wiki/images"
_HEADERS = {"User-Agent": "The Iron Foundry Project / contact@ironfoundry.cc"}
_IMAGE_RE = re.compile(r"\[\[File:([^\|]+)")


def _npc_icon_url(image_field: str) -> str:
    m = _IMAGE_RE.search(image_field)
    filename = m.group(1) if m else image_field
    return f"{_WIKI_IMAGES}/{filename.strip().replace(' ', '_')}"


@router.get("/osrs/npcs")
async def search_osrs_npcs(q: str = Query("", min_length=0)) -> list[dict[str, Any]]:
    """Search OSRS NPC names for the tile editor. Needs at least two characters."""
    if not q or len(q) < 2:
        return []
    safe_q = q.replace("'", "''").replace(";", "")[:50]
    params = {
        "action": "cargoquery",
        "tables": "Monsters",
        "fields": "Monsters._pageID=id,Monsters._pageName=name,Monsters.image=image",
        "where": f"Monsters._pageName LIKE '%{safe_q}%'",
        "order_by": "Monsters._pageName",
        "limit": "10",
        "format": "json",
    }
    try:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=10.0) as client:
            resp = await client.get(_WIKI_API, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("OSRS NPC search failed: {}", exc)
        return []
    results = []
    for row in data.get("cargoquery", []):
        title = row.get("title", {})
        name = title.get("name", "")
        image = title.get("image", "")
        if name and image:
            results.append(
                {
                    "id": int(title.get("id") or 0),
                    "name": name,
                    "icon_url": _npc_icon_url(image),
                }
            )
    return results
