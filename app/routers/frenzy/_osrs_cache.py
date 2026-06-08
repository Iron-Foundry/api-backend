from __future__ import annotations

import json

import httpx
from loguru import logger
from valkey.asyncio import Valkey

from app.services.http import WiseOldManHandler

from ._constants import (
    _ACTIVITIES_KEY, _ACTIVITY_METRICS, _BOSS_METRICS, _BOSSES_KEY, _ITEMS_KEY,
    _LB_FRESH_KEY, _LB_FRESH_TTL, _LB_LOCK_KEY, _LB_LOCK_TTL, _LB_STALE_KEY,
    _LB_STALE_TTL, _OSRS_REF_TTL, _WIKI_IMAGE_BASE, _WOM_API_KEY,
    _WOM_DISCORD_CONTACT, _WOM_GROUP_ID, _wiki_icon,
)


async def _refresh_osrs_items(valkey: Valkey) -> None:
    async with httpx.AsyncClient(
        headers={"User-Agent": "The Iron Foundry Project / contact@ironfoundry.cc"},
        timeout=20.0,
    ) as client:
        resp = await client.get("https://prices.runescape.wiki/api/v1/osrs/mapping")
        resp.raise_for_status()
        raw = resp.json()
    items = [
        {
            "id": entry["id"],
            "name": entry["name"],
            "icon_url": f"{_WIKI_IMAGE_BASE}/{entry['icon'].replace(' ', '_')}",
            "members": entry.get("members", False),
        }
        for entry in raw
        if entry.get("name") and entry.get("icon")
    ]
    await valkey.setex(_ITEMS_KEY, _OSRS_REF_TTL, json.dumps(items))
    logger.info("osrs items cache: loaded {} items", len(items))


async def _refresh_osrs_bosses(valkey: Valkey) -> None:
    bosses = [
        {"slug": slug, "name": name, "icon_url": _wiki_icon(icon_slug)}
        for slug, (name, icon_slug) in _BOSS_METRICS.items()
    ]
    await valkey.setex(_BOSSES_KEY, _OSRS_REF_TTL, json.dumps(bosses))
    logger.info("osrs bosses cache: loaded {} bosses", len(bosses))


async def _refresh_osrs_activities(valkey: Valkey) -> None:
    activities = [
        {"slug": slug, "name": name, "icon_url": _wiki_icon(icon_slug)}
        for slug, (name, icon_slug) in _ACTIVITY_METRICS.items()
    ]
    await valkey.setex(_ACTIVITIES_KEY, _OSRS_REF_TTL, json.dumps(activities))
    logger.info("osrs activities cache: loaded {} activities", len(activities))


async def warm_osrs_caches(valkey: Valkey) -> None:
    """Called from app lifespan to pre-populate OSRS reference data."""
    if not await valkey.exists(_ITEMS_KEY):
        await _refresh_osrs_items(valkey)
    if not await valkey.exists(_BOSSES_KEY):
        await _refresh_osrs_bosses(valkey)
    if not await valkey.exists(_ACTIVITIES_KEY):
        await _refresh_osrs_activities(valkey)


async def _build_lb_cache(valkey: Valkey, wom_comp_id: int | None, metrics: list[str]) -> None:
    acquired = await valkey.set(_LB_LOCK_KEY, "1", ex=_LB_LOCK_TTL, nx=True)
    if not acquired:
        return
    try:
        out: list[dict] = []
        async with WiseOldManHandler(api_key=_WOM_API_KEY, discord_contact=_WOM_DISCORD_CONTACT, timeout=15.0) as wom:
            for metric in metrics:
                entries = await wom.fetch_kc_metric(_WOM_GROUP_ID, metric)
                if entries:
                    boss_name, _ = _BOSS_METRICS.get(metric, (metric, metric))
                    out.append({"metric": metric, "display_name": boss_name, "entries": entries})

        if out:
            payload = json.dumps(out)
            await valkey.setex(_LB_FRESH_KEY, _LB_FRESH_TTL, payload)
            await valkey.setex(_LB_STALE_KEY, _LB_STALE_TTL, payload)
    finally:
        await valkey.delete(_LB_LOCK_KEY)
