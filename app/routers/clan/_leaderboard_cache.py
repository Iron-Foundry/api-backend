from __future__ import annotations

import json

from loguru import logger
from valkey.asyncio import Valkey

from app.services.http import WiseOldManHandler, WomPriority

from ._constants import (
    _KC_FRESH_KEY,
    _KC_FRESH_TTL,
    _KC_LOCK_KEY,
    _KC_LOCK_TTL,
    _KC_METRICS,
    _KC_STALE_KEY,
    _KC_STALE_TTL,
    _CLUESCROLLS_FRESH_KEY,
    _CLUESCROLLS_FRESH_TTL,
    _CLUESCROLLS_LOCK_KEY,
    _CLUESCROLLS_LOCK_TTL,
    _CLUESCROLLS_METRICS,
    _CLUESCROLLS_STALE_KEY,
    _CLUESCROLLS_STALE_TTL,
    _WOM_API_KEY,
    _WOM_DISCORD_CONTACT,
    _WOM_GROUP_ID,
)


async def _fetch_bulk_hiscores() -> list[dict] | None:
    """Fetch clan bulk hiscores. Returns None (logged) on any WOM failure."""
    try:
        async with WiseOldManHandler(
            api_key=_WOM_API_KEY,
            discord_contact=_WOM_DISCORD_CONTACT,
            timeout=15.0,
            priority=WomPriority.LOW,
        ) as wom:
            return await wom.get_group_bulk_hiscores(_WOM_GROUP_ID)
    except Exception as exc:
        logger.warning("leaderboard cache: WOM bulk-hiscores fetch failed: {}", exc)
        return None


def _bucket_bulk_by_metric(
    bulk: list[dict], metrics: dict[str, str], category: str, value_key: str
) -> list[dict]:
    """Bucket a bulk-hiscores response into one ranked leaderboard per metric."""
    out: list[dict] = []
    for metric, display_name in metrics.items():
        entries: list[dict] = []
        for entry in bulk:
            snapshot = (entry.get("data") or {}).get("data")
            if not snapshot:
                continue
            info = (snapshot.get(category) or {}).get(metric)
            value = info.get(value_key) if isinstance(info, dict) else None
            if value:
                entries.append(
                    {"player_name": entry["player"]["displayName"], value_key: value}
                )
        if entries:
            entries.sort(key=lambda e: e[value_key], reverse=True)
            out.append(
                {"metric": metric, "display_name": display_name, "entries": entries}
            )
    return out


async def _build_kc_cache(valkey: Valkey) -> None:
    """Fetch clan bulk hiscores once and bucket into per-boss KC leaderboards."""
    acquired = await valkey.set(_KC_LOCK_KEY, "1", ex=_KC_LOCK_TTL, nx=True)
    if not acquired:
        return
    try:
        bulk = await _fetch_bulk_hiscores()
        if bulk is None:
            return
        out = _bucket_bulk_by_metric(bulk, _KC_METRICS, "bosses", "kills")
        if out:
            payload = json.dumps(out)
            await valkey.setex(_KC_FRESH_KEY, _KC_FRESH_TTL, payload)
            await valkey.setex(_KC_STALE_KEY, _KC_STALE_TTL, payload)
    finally:
        await valkey.delete(_KC_LOCK_KEY)


async def _build_cluescrolls_cache(valkey: Valkey) -> None:
    """Fetch clan bulk hiscores once and bucket into per-tier clue scroll leaderboards."""
    acquired = await valkey.set(
        _CLUESCROLLS_LOCK_KEY, "1", ex=_CLUESCROLLS_LOCK_TTL, nx=True
    )
    if not acquired:
        return
    try:
        bulk = await _fetch_bulk_hiscores()
        if bulk is None:
            return
        out = _bucket_bulk_by_metric(bulk, _CLUESCROLLS_METRICS, "activities", "score")
        if out:
            payload = json.dumps(out)
            await valkey.setex(_CLUESCROLLS_FRESH_KEY, _CLUESCROLLS_FRESH_TTL, payload)
            await valkey.setex(_CLUESCROLLS_STALE_KEY, _CLUESCROLLS_STALE_TTL, payload)
    finally:
        await valkey.delete(_CLUESCROLLS_LOCK_KEY)
