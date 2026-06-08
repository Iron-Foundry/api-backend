from __future__ import annotations

import json

from valkey.asyncio import Valkey

from app.services.http import WiseOldManHandler, WomPriority

from ._constants import (
    _KC_FRESH_KEY, _KC_FRESH_TTL, _KC_LOCK_KEY, _KC_LOCK_TTL, _KC_METRICS,
    _KC_STALE_KEY, _KC_STALE_TTL, _LEAGUES_FRESH_KEY, _LEAGUES_FRESH_TTL,
    _LEAGUES_LOCK_KEY, _LEAGUES_LOCK_TTL, _LEAGUES_STALE_KEY, _LEAGUES_STALE_TTL,
    _WOM_API_KEY, _WOM_DISCORD_CONTACT, _WOM_GROUP_ID,
)


async def _build_kc_cache(valkey: Valkey) -> None:
    """Sequential, rate-limit-aware population of the KC leaderboard cache."""
    acquired = await valkey.set(_KC_LOCK_KEY, "1", ex=_KC_LOCK_TTL, nx=True)
    if not acquired:
        return
    try:
        async with WiseOldManHandler(api_key=_WOM_API_KEY, discord_contact=_WOM_DISCORD_CONTACT, timeout=15.0, priority=WomPriority.LOW) as wom:
            out: list[dict] = []
            for metric, display_name in _KC_METRICS.items():
                entries = await wom.fetch_kc_metric(_WOM_GROUP_ID, metric)
                if entries:
                    out.append({"metric": metric, "display_name": display_name, "entries": entries})
        if out:
            payload = json.dumps(out)
            await valkey.setex(_KC_FRESH_KEY, _KC_FRESH_TTL, payload)
            await valkey.setex(_KC_STALE_KEY, _KC_STALE_TTL, payload)
    finally:
        await valkey.delete(_KC_LOCK_KEY)


async def _build_leagues_cache(valkey: Valkey) -> None:
    """Paginate WOM group hiscores for clue_scrolls_all and cache the ranked list."""
    acquired = await valkey.set(_LEAGUES_LOCK_KEY, "1", ex=_LEAGUES_LOCK_TTL, nx=True)
    if not acquired:
        return
    try:
        entries: list[dict] = []
        limit = 50
        offset = 0
        async with WiseOldManHandler(api_key=_WOM_API_KEY, discord_contact=_WOM_DISCORD_CONTACT, timeout=15.0, priority=WomPriority.LOW) as wom:
            while True:
                page = await wom.get_group_hiscores(_WOM_GROUP_ID, "clue_scrolls_all", limit=limit, offset=offset)
                if not page:
                    break
                for e in page:
                    score = (e.get("data") or {}).get("score") or 0
                    if score > 0:
                        entries.append({"player_name": e["player"]["displayName"], "score": score})
                if len(page) < limit:
                    break
                offset += limit
        if entries:
            payload = json.dumps(entries)
            await valkey.setex(_LEAGUES_FRESH_KEY, _LEAGUES_FRESH_TTL, payload)
            await valkey.setex(_LEAGUES_STALE_KEY, _LEAGUES_STALE_TTL, payload)
    finally:
        await valkey.delete(_LEAGUES_LOCK_KEY)
