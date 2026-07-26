"""Resolves drop item names to cache item ids via the osrs-cache-service."""

from __future__ import annotations

import os

import httpx
from loguru import logger

OSRS_CACHE_SERVICE_URL = os.getenv(
    "OSRS_CACHE_SERVICE_URL", "http://osrs-cache-service:8100"
)


async def fetch_item_index() -> dict[str, int]:
    """Return a lowercased item-name to item-id map, or empty on failure."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{OSRS_CACHE_SERVICE_URL}/items/names")
    except httpx.RequestError as exc:
        logger.warning("loot_tables: cache service unavailable for item names: {}", exc)
        return {}
    if resp.status_code != 200:
        return {}
    index: dict[str, int] = {}
    for item_id, name in resp.json().items():
        key = name.strip().lower()
        if key:
            index.setdefault(key, int(item_id))
    return index


def resolve_item_id(name: str, index: dict[str, int]) -> int | None:
    return index.get(name.strip().lower())
