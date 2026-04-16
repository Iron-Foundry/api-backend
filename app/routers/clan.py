"""Clan router — public read endpoints for clan stats and activity."""

from __future__ import annotations

import asyncio
import json
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

from app.db.models import Event, Leaderboard, Metric, User
from app.dependencies import get_current_user, get_session, get_valkey

router = APIRouter(prefix="/clan", tags=["clan"])

_WOM_GROUP_ID = os.getenv("WOM_GROUP_ID", "9403")
_WOM_CACHE_KEY = "clan:wom_stats"
_WOM_TTL = 5 * 60  # 5 minutes

# Raid metric slugs on WOM (mirror OSRS hiscores activity names)
_RAID_METRICS = [
    "chambers_of_xeric",
    "chambers_of_xeric_challenge_mode",
    "theatre_of_blood",
    "theatre_of_blood_hard_mode",
    "tombs_of_amascut",
    "tombs_of_amascut_expert_mode",
]


async def _fetch_metric_total(client: httpx.AsyncClient, group_id: str, metric: str) -> int:
    """Sum `data.kills` across all group members for a single WOM metric."""
    total = 0
    limit = 50
    offset = 0
    while True:
        resp = await client.get(
            f"https://api.wiseoldman.net/v2/groups/{group_id}/hiscores",
            params={"metric": metric, "limit": limit, "offset": offset},
            headers={"User-Agent": "IronFoundry/1.0"},
        )
        if not resp.is_success:
            break
        page: list[dict] = resp.json()
        if not page:
            break
        for entry in page:
            total += entry.get("data", {}).get("kills", 0) or 0
        if len(page) < limit:
            break
        offset += limit
    return total

_DROP_MIN_VALUE = 2_000_000      # 2M gp
_XP_MIN_MILESTONE = 15_000_000   # 15M xp
_XP_STEP = 5_000_000             # every 5M xp


@router.get("/wom-stats")
async def wom_stats(valkey: Valkey = Depends(get_valkey)) -> dict:
    """Return WiseOldMan group summary (member count, total XP, total EHB).

    Cached in Valkey for 5 minutes to avoid hitting WOM's rate limit on every
    page load.
    """
    cached = await valkey.get(_WOM_CACHE_KEY)
    if cached:
        return json.loads(cached)

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Fetch group summary and all raid hiscores concurrently
        group_coro = client.get(
            f"https://api.wiseoldman.net/v2/groups/{_WOM_GROUP_ID}",
            headers={"User-Agent": "IronFoundry/1.0"},
        )
        raid_coros = [
            _fetch_metric_total(client, _WOM_GROUP_ID, m) for m in _RAID_METRICS
        ]
        group_resp, *raid_totals = await asyncio.gather(group_coro, *raid_coros, return_exceptions=True)

    if isinstance(group_resp, Exception) or not group_resp.is_success:
        if not isinstance(group_resp, Exception) and group_resp.status_code == 429:
            raise HTTPException(status_code=429, detail="WiseOldMan rate limit reached — try again shortly.")
        raise HTTPException(status_code=502, detail="Failed to fetch WiseOldMan data.")

    raw = group_resp.json()
    memberships = raw.get("memberships") or []

    def _safe_int(v: object) -> int:
        return v if isinstance(v, int) else 0

    metric_totals = {m: _safe_int(t) for m, t in zip(_RAID_METRICS, raid_totals)}

    result = {
        "member_count": raw.get("memberCount", 0),
        "total_xp": sum(m.get("player", {}).get("exp", 0) for m in memberships),
        "total_ehb": round(sum(m.get("player", {}).get("ehb", 0.0) for m in memberships)),
        "cox_kc": metric_totals["chambers_of_xeric"] + metric_totals["chambers_of_xeric_challenge_mode"],
        "tob_kc": metric_totals["theatre_of_blood"] + metric_totals["theatre_of_blood_hard_mode"],
        "toa_kc": metric_totals["tombs_of_amascut"] + metric_totals["tombs_of_amascut_expert_mode"],
    }
    await valkey.setex(_WOM_CACHE_KEY, _WOM_TTL, json.dumps(result))
    return result


@router.get("/stats")
async def clan_stats(session: AsyncSession = Depends(get_session)) -> dict:
    """Return aggregate clan stats: total GP looted and total collection log items."""
    gp_result = await session.execute(
        select(
            func.coalesce(
                func.sum(Event.data["coin_value"].as_integer()), 0
            )
        ).where(Event.type.in_(["loot", "loot_key", "clue_item"]))
    )
    total_gp = gp_result.scalar_one() or 0

    cl_result = await session.execute(
        select(func.coalesce(func.sum(User.collection_log_slots), 0))
    )
    collection_log_items = cl_result.scalar_one() or 0

    clog_result = await session.execute(
        select(Metric.count).where(Metric.id == "total_clogs")
    )
    total_clogs = clog_result.scalar_one_or_none() or 0

    return {
        "total_gp": total_gp,
        "collection_log_items": collection_log_items,
        "total_clogs": total_clogs,
    }


@router.get("/recent-achievements")
async def recent_achievements(
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Return recent notable clan achievements across drops, levels, and XP milestones.

    Filters applied:
    - Drops: coin_value >= 2M
    - Levels: 99s and Total Level events
    - XP milestones: >= 15M xp
    """
    results: list[dict] = []

    # Notable drops
    drop_result = await session.execute(
        select(Event)
        .where(
            Event.type.in_(["loot", "loot_key", "clue_item"]),
            Event.data["coin_value"].as_integer() >= _DROP_MIN_VALUE,
        )
        .order_by(Event.timestamp.desc())
        .limit(limit)
    )
    for row in drop_result.scalars():
        d = row.data or {}
        results.append({
            "type": "drop",
            "player": row.player_name,
            "label": d.get("item_name", ""),
            "detail": d.get("source") or None,
            "value": d.get("coin_value", 0),
            "timestamp": row.timestamp.isoformat(),
        })

    # 99s and Total Level milestones
    level_result = await session.execute(
        select(Event)
        .where(
            Event.type == "level",
            Event.data["new_level"].as_integer() == 99,
        )
        .order_by(Event.timestamp.desc())
        .limit(limit)
    )
    for row in level_result.scalars():
        d = row.data or {}
        skill = d.get("skill", "")
        results.append({
            "type": "level",
            "player": row.player_name,
            "label": "Total Level" if skill == "total" else skill,
            "detail": None,
            "value": d.get("new_level", 0),
            "timestamp": row.timestamp.isoformat(),
        })

    # Also total level events
    total_level_result = await session.execute(
        select(Event)
        .where(
            Event.type == "level",
            Event.data["skill"].as_string() == "total",
        )
        .order_by(Event.timestamp.desc())
        .limit(limit)
    )
    for row in total_level_result.scalars():
        d = row.data or {}
        results.append({
            "type": "level",
            "player": row.player_name,
            "label": "Total Level",
            "detail": None,
            "value": d.get("new_level", 0),
            "timestamp": row.timestamp.isoformat(),
        })

    # XP milestones >= 15M (divisible by 5M)
    xp_result = await session.execute(
        select(Event)
        .where(
            Event.type == "xp_milestone",
            Event.data["xp"].as_integer() >= _XP_MIN_MILESTONE,
            func.mod(Event.data["xp"].as_integer(), _XP_STEP) == 0,
        )
        .order_by(Event.timestamp.desc())
        .limit(limit)
    )
    for row in xp_result.scalars():
        d = row.data or {}
        results.append({
            "type": "xp_milestone",
            "player": row.player_name,
            "label": d.get("skill", ""),
            "detail": None,
            "value": d.get("xp", 0),
            "timestamp": row.timestamp.isoformat(),
        })

    results.sort(key=lambda x: x["timestamp"], reverse=True)
    return results[:limit]


@router.get("/leaderboards")
async def clan_leaderboards(session: AsyncSession = Depends(get_session)) -> list[dict]:
    """Return all personal best entries from the leaderboards table, sorted by activity then time."""
    result = await session.execute(
        select(Leaderboard).order_by(
            Leaderboard.activity,
            Leaderboard.variant,
            Leaderboard.time_seconds,
        )
    )
    return [
        {
            "player_name": r.player_name,
            "activity": r.activity,
            "variant": r.variant,
            "time_seconds": r.time_seconds,
        }
        for r in result.scalars()
    ]


@router.get("/user-avatar/{user_id}")
async def user_avatar(
    user_id: int,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return the stored Discord avatar URL for the given user ID."""
    result = await session.execute(
        select(User.discord_avatar_url).where(User.discord_user_id == user_id)
    )
    avatar_url = result.scalar_one_or_none()
    if not avatar_url:
        raise HTTPException(status_code=404, detail="Avatar not available.")
    return {"avatar_url": avatar_url}
