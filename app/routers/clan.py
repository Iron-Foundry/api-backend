"""Clan router — public read endpoints for clan stats and activity."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pymongo.asynchronous.database import AsyncDatabase

from app.dependencies import get_db

router = APIRouter(prefix="/clan", tags=["clan"])

_DROP_MIN_VALUE = 2_000_000      # 2M gp
_XP_MIN_MILESTONE = 15_000_000   # 15M xp
_XP_STEP = 5_000_000             # every 5M xp


@router.get("/recent-achievements")
async def recent_achievements(
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncDatabase = Depends(get_db),
) -> list[dict]:
    """Return recent notable clan achievements across drops, levels, and XP milestones.

    Filters applied:
    - Drops: coin_value >= 2M
    - Levels: 99s and Total Level events
    - XP milestones: >= 15M xp
    """
    results: list[dict] = []

    # Notable drops
    async for doc in (
        db["loot_events"]
        .find(
            {"coin_value": {"$gte": _DROP_MIN_VALUE}},
            {"player_name": 1, "item_name": 1, "coin_value": 1, "source": 1, "timestamp": 1, "_id": 0},
        )
        .sort("timestamp", -1)
        .limit(limit)
    ):
        results.append({
            "type": "drop",
            "player": doc["player_name"],
            "label": doc["item_name"],
            "detail": doc.get("source") or None,
            "value": doc.get("coin_value", 0),
            "timestamp": doc["timestamp"].isoformat(),
        })

    # 99s and Total Level milestones
    async for doc in (
        db["level_events"]
        .find(
            {"$or": [{"new_level": 99}, {"skill": "Total Level"}]},
            {"player_name": 1, "skill": 1, "new_level": 1, "timestamp": 1, "_id": 0},
        )
        .sort("timestamp", -1)
        .limit(limit)
    ):
        results.append({
            "type": "level",
            "player": doc["player_name"],
            "label": doc["skill"],
            "detail": None,
            "value": doc.get("new_level", 0),
            "timestamp": doc["timestamp"].isoformat(),
        })

    # XP milestones >= 15M
    async for doc in (
        db["xp_events"]
        .find(
            {"xp": {"$gte": _XP_MIN_MILESTONE, "$mod": [_XP_STEP, 0]}},
            {"player_name": 1, "skill": 1, "xp": 1, "timestamp": 1, "_id": 0},
        )
        .sort("timestamp", -1)
        .limit(limit)
    ):
        results.append({
            "type": "xp_milestone",
            "player": doc["player_name"],
            "label": doc["skill"],
            "detail": None,
            "value": doc.get("xp", 0),
            "timestamp": doc["timestamp"].isoformat(),
        })

    results.sort(key=lambda x: x["timestamp"], reverse=True)
    return results[:limit]
