from __future__ import annotations

import json
from typing import Any

import httpx
from loguru import logger
from valkey.asyncio import Valkey

from app.services.http import WiseOldManHandler

from ._constants import (
    _ACTIVITIES_KEY,
    _ACTIVITY_METRICS,
    _BOSS_METRICS,
    _BOSSES_KEY,
    _ITEM_ICON_BASE,
    _ITEMS_KEY,
    _LB_FRESH_KEY,
    _LB_FRESH_TTL,
    _LB_LOCK_KEY,
    _LB_LOCK_TTL,
    _LB_STALE_KEY,
    _LB_STALE_TTL,
    _OSRS_CACHE_SERVICE_URL,
    _OSRS_REF_TTL,
    _WOM_API_KEY,
    _WOM_DISCORD_CONTACT,
    _WOM_GROUP_ID,
    _wiki_icon,
)


async def _refresh_osrs_items(valkey: Valkey) -> None:
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(f"{_OSRS_CACHE_SERVICE_URL}/items/catalog")
        resp.raise_for_status()
        raw = resp.json()
    items = [
        {
            "id": entry["item_id"],
            "name": entry["name"],
            "icon_url": f"{_ITEM_ICON_BASE}/{entry['item_id']}",
            "members": entry.get("members", False),
        }
        for entry in raw
        if entry.get("name")
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
    """Called from app lifespan to pre-populate OSRS reference data.

    Best-effort: the request path refreshes each cache on miss, so a warm
    failure (e.g. the osrs-cache service unreachable at boot) must log and
    continue rather than abort application startup.
    """
    for key, refresh in (
        (_ITEMS_KEY, _refresh_osrs_items),
        (_BOSSES_KEY, _refresh_osrs_bosses),
        (_ACTIVITIES_KEY, _refresh_osrs_activities),
    ):
        if await valkey.exists(key):
            continue
        try:
            await refresh(valkey)
        except Exception as exc:
            logger.warning("osrs cache warm for {} skipped: {}", key, exc)


def _lb_display_name(metric: str) -> str:
    if metric in _BOSS_METRICS:
        return _BOSS_METRICS[metric][0]
    return _ACTIVITY_METRICS.get(metric, (metric, metric))[0]


async def _build_lb_cache(
    valkey: Valkey, wom_comp_id: int | None, metrics: list[str]
) -> None:
    """Fetch clan bulk hiscores once and bucket into per-metric event leaderboards."""
    acquired = await valkey.set(_LB_LOCK_KEY, "1", ex=_LB_LOCK_TTL, nx=True)
    if not acquired:
        return
    try:
        try:
            async with WiseOldManHandler(
                api_key=_WOM_API_KEY, discord_contact=_WOM_DISCORD_CONTACT, timeout=15.0
            ) as wom:
                bulk = await wom.get_group_bulk_hiscores(_WOM_GROUP_ID)
        except Exception as exc:
            logger.warning(
                "frenzy leaderboard cache: WOM bulk-hiscores fetch failed: {}", exc
            )
            return

        out: list[dict[str, Any]] = []
        for metric in metrics:
            category = "bosses" if metric in _BOSS_METRICS else "activities"
            rows: list[tuple[str, int]] = []
            for entry in bulk:
                snapshot = (entry.get("data") or {}).get("data")
                if not snapshot:
                    continue
                info = (snapshot.get(category) or {}).get(metric)
                if not isinstance(info, dict):
                    continue
                value = info.get("kills") if category == "bosses" else info.get("score")
                if value:
                    rows.append((entry["player"]["displayName"], value))
            if not rows:
                continue
            rows.sort(key=lambda r: r[1], reverse=True)
            out.append(
                {
                    "metric": metric,
                    "display_name": _lb_display_name(metric),
                    "entries": [
                        {"index": i + 1, "rsn": rsn, "value": value}
                        for i, (rsn, value) in enumerate(rows)
                    ],
                }
            )

        if out:
            payload = json.dumps(out)
            await valkey.setex(_LB_FRESH_KEY, _LB_FRESH_TTL, payload)
            await valkey.setex(_LB_STALE_KEY, _LB_STALE_TTL, payload)
    finally:
        await valkey.delete(_LB_LOCK_KEY)
