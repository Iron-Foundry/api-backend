from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ClanStats, Event, Metric
from app.dependencies import get_session

from ._constants import _DROP_MIN_VALUE, _XP_MIN_MILESTONE, _XP_STEP

router = APIRouter()


@router.get("/wom-stats")
async def wom_stats(session: AsyncSession = Depends(get_session)) -> dict:
    """Return the latest WOM clan stat snapshot written by ClanStatsService."""
    result = await session.execute(select(ClanStats).where(ClanStats.id == 1))
    row = result.scalar_one_or_none()
    if row is None:
        return {"member_count": 0, "total_xp": 0, "total_ehb": 0, "cox_kc": 0, "tob_kc": 0, "toa_kc": 0, "updated_at": None}
    return {
        "member_count": row.member_count or 0, "total_xp": row.total_xp or 0,
        "total_ehb": row.total_ehb or 0, "cox_kc": row.cox_kc or 0,
        "tob_kc": row.tob_kc or 0, "toa_kc": row.toa_kc or 0,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/stats")
async def clan_stats(session: AsyncSession = Depends(get_session)) -> dict:
    """Return aggregate clan stats: total GP looted and total collection log items."""
    gp_result = await session.execute(
        select(func.coalesce(func.sum(Event.data["coin_value"].as_integer()), 0))
        .where(Event.type.in_(["loot", "loot_key", "clue_item"]))
    )
    total_gp = gp_result.scalar_one() or 0

    per_player = (
        select(func.max(Event.data["log_slots"].as_integer()).label("max_slots"))
        .where(Event.type == "collection_log", Event.player_name.is_not(None), Event.is_league_world.is_(False))
        .group_by(Event.player_name)
        .subquery()
    )
    cl_result = await session.execute(select(func.coalesce(func.sum(per_player.c.max_slots), 0)))
    collection_log_items = cl_result.scalar_one() or 0

    clog_result = await session.execute(select(Metric.count).where(Metric.id == "total_clogs"))
    total_clogs = clog_result.scalar_one_or_none() or 0

    return {"total_gp": total_gp, "collection_log_items": collection_log_items, "total_clogs": total_clogs}


@router.get("/recent-achievements")
async def recent_achievements(
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Return recent notable clan achievements: drops >=2M, 99s, total levels, and XP milestones >=15M."""
    results: list[dict] = []

    drop_result = await session.execute(
        select(Event)
        .where(Event.type.in_(["loot", "loot_key", "clue_item"]), Event.data["coin_value"].as_integer() >= _DROP_MIN_VALUE)
        .order_by(Event.timestamp.desc()).limit(limit)
    )
    for row in drop_result.scalars():
        d = row.data or {}
        results.append({"type": "drop", "player": row.player_name, "label": d.get("item_name", ""), "detail": d.get("source") or None, "value": d.get("coin_value", 0), "timestamp": row.timestamp.isoformat()})

    level_result = await session.execute(
        select(Event).where(Event.type == "level", Event.data["new_level"].as_integer() == 99)
        .order_by(Event.timestamp.desc()).limit(limit)
    )
    for row in level_result.scalars():
        d = row.data or {}
        skill = d.get("skill", "")
        results.append({"type": "level", "player": row.player_name, "label": "Total Level" if skill == "total" else skill, "detail": None, "value": d.get("new_level", 0), "timestamp": row.timestamp.isoformat()})

    total_level_result = await session.execute(
        select(Event).where(Event.type == "level", Event.data["skill"].as_string() == "total")
        .order_by(Event.timestamp.desc()).limit(limit)
    )
    for row in total_level_result.scalars():
        d = row.data or {}
        results.append({"type": "level", "player": row.player_name, "label": "Total Level", "detail": None, "value": d.get("new_level", 0), "timestamp": row.timestamp.isoformat()})

    xp_result = await session.execute(
        select(Event)
        .where(Event.type == "xp_milestone", Event.data["xp"].as_integer() >= _XP_MIN_MILESTONE, func.mod(Event.data["xp"].as_integer(), _XP_STEP) == 0)
        .order_by(Event.timestamp.desc()).limit(limit)
    )
    for row in xp_result.scalars():
        d = row.data or {}
        results.append({"type": "xp_milestone", "player": row.player_name, "label": d.get("skill", ""), "detail": None, "value": d.get("xp", 0), "timestamp": row.timestamp.isoformat()})

    results.sort(key=lambda x: x["timestamp"], reverse=True)
    return results[:limit]
