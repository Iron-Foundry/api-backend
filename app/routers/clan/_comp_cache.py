from __future__ import annotations

import json
from datetime import datetime, timezone

from loguru import logger
from valkey.asyncio import Valkey

from app.services.http import WiseOldManHandler, WomPriority

from ._constants import (
    _COMP_METRIC_STALE_TTL,
    _COMPS_FRESH_KEY,
    _COMPS_FRESH_TTL,
    _COMPS_LOCK_KEY,
    _COMPS_STALE_KEY,
    _COMPS_STALE_TTL,
    _WOM_API_KEY,
    _WOM_DISCORD_CONTACT,
    _WOM_GROUP_ID,
)
from ._helpers import _comp_metric_fresh_ttl, _comp_metric_keys


async def _build_competitions_cache(valkey: Valkey) -> None:
    logger.info("competitions cache: hydrating from WOM (group={})", _WOM_GROUP_ID)
    try:
        wom = WiseOldManHandler(
            api_key=_WOM_API_KEY,
            discord_contact=_WOM_DISCORD_CONTACT,
            priority=WomPriority.NORMAL,
        )
        comps = await wom.get_all_group_competitions(_WOM_GROUP_ID)
        if comps:
            payload = json.dumps(comps)
            await valkey.setex(_COMPS_FRESH_KEY, _COMPS_FRESH_TTL, payload)
            await valkey.setex(_COMPS_STALE_KEY, _COMPS_STALE_TTL, payload)
            statuses: dict[str, int] = {}
            for c in comps:
                statuses[c["status"]] = statuses.get(c["status"], 0) + 1
            logger.info(
                "competitions cache: wrote {} competitions ({})",
                len(comps),
                ", ".join(f"{v} {k}" for k, v in statuses.items()),
            )
        else:
            logger.warning(
                "competitions cache: WOM returned empty list - cache not updated"
            )
    except Exception as exc:
        logger.error("competitions cache: hydration failed - {}", exc)
    finally:
        await valkey.delete(_COMPS_LOCK_KEY)


async def _invalidate_competitions_cache(valkey: Valkey) -> None:
    """Delete fresh cache + lock so the next request triggers a rebuild. Leaves stale intact."""
    await valkey.delete(_COMPS_FRESH_KEY)
    await valkey.delete(_COMPS_LOCK_KEY)
    logger.info("competitions cache: invalidated after write operation")


async def _build_metric_detail_cache(
    comp_id: int, metric: str, status: str, valkey: Valkey
) -> None:
    """Fetch competition details for a specific metric and write to Valkey cache."""
    fresh_key, stale_key, lock_key = _comp_metric_keys(comp_id, metric)
    logger.info("comp metric cache: hydrating comp={} metric={}", comp_id, metric)
    try:
        async with WiseOldManHandler(
            api_key=_WOM_API_KEY,
            discord_contact=_WOM_DISCORD_CONTACT,
            priority=WomPriority.NORMAL,
        ) as wom:
            data = await wom.get_competition_details(comp_id, metric=metric)

        starts_at = datetime.fromisoformat(data["startsAt"].replace("Z", "+00:00"))
        ends_at = datetime.fromisoformat(data["endsAt"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        if now < starts_at:
            status = "upcoming"
        elif now <= ends_at:
            status = "ongoing"
        else:
            status = "finished"

        def _safe_num(v: object) -> int | float:
            return v if isinstance(v, (int, float)) else 0

        raw_parts: list[dict] = []
        for p in data.get("participations", []):
            progress = p.get("progress") or {}
            raw_parts.append(
                {
                    "player_name": p["player"]["displayName"],
                    "team_name": p.get("teamName"),
                    "gained": _safe_num(progress.get("gained")),
                    "start": _safe_num(progress.get("start")),
                    "end": _safe_num(progress.get("end")),
                }
            )
        raw_parts.sort(key=lambda x: x["gained"], reverse=True)
        for i, part in enumerate(raw_parts, 1):
            part["rank"] = i

        payload = json.dumps(
            {
                "id": data["id"],
                "title": data["title"],
                "metric": metric,
                "type": data.get("type", "classic"),
                "status": status,
                "startsAt": data["startsAt"],
                "endsAt": data["endsAt"],
                "participations": raw_parts,
            }
        )
        fresh_ttl = _comp_metric_fresh_ttl(status)
        await valkey.setex(fresh_key, fresh_ttl, payload)
        await valkey.setex(stale_key, _COMP_METRIC_STALE_TTL, payload)
        logger.info(
            "comp metric cache: wrote comp={} metric={} participants={}",
            comp_id,
            metric,
            len(raw_parts),
        )
    except Exception as exc:
        logger.error(
            "comp metric cache: hydration failed comp={} metric={} - {}",
            comp_id,
            metric,
            exc,
        )
    finally:
        await valkey.delete(lock_key)
