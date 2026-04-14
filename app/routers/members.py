"""Members router — authenticated endpoints for profile self-management."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel
from pymongo.asynchronous.database import AsyncDatabase

from app.dependencies import get_current_user, get_db

router = APIRouter(prefix="/members", tags=["members"])

_RSN_RE = re.compile(r"^[A-Za-z0-9 _-]{1,12}$")


# ── request bodies ─────────────────────────────────────────────────────────


class PrivacyUpdate(BaseModel):
    stats_opt_out: bool


class RsnUpdate(BaseModel):
    rsn: str


# ── endpoints ──────────────────────────────────────────────────────────────


@router.patch("/me/privacy")
async def update_privacy(
    body: PrivacyUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
) -> dict:
    """Toggle stats opt-out for the authenticated user."""
    discord_user_id = int(current_user["sub"])
    await db["users"].update_one(
        {"discord_user_id": discord_user_id},
        {
            "$set": {
                "stats_opt_out": body.stats_opt_out,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    logger.info(
        "members/privacy: user {} set stats_opt_out={}",
        discord_user_id,
        body.stats_opt_out,
    )
    return {"stats_opt_out": body.stats_opt_out}


@router.patch("/me/rsn")
async def update_rsn(
    body: RsnUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
) -> dict:
    """Update the RSN linked to the authenticated user's account."""
    rsn = body.rsn.strip()
    if not rsn:
        raise HTTPException(status_code=422, detail="RSN cannot be empty.")
    if not _RSN_RE.match(rsn):
        raise HTTPException(
            status_code=422,
            detail="RSN must be 1–12 characters: letters, numbers, spaces, hyphens, underscores.",
        )

    discord_user_id = int(current_user["sub"])

    # Check the RSN isn't already claimed by a different user.
    existing = await db["users"].find_one(
        {"rsn": {"$regex": f"^{re.escape(rsn)}$", "$options": "i"}},
        {"discord_user_id": 1},
    )
    if existing and existing["discord_user_id"] != discord_user_id:
        raise HTTPException(status_code=409, detail="That RSN is linked to another account.")

    await db["users"].update_one(
        {"discord_user_id": discord_user_id},
        {
            "$set": {
                "rsn": rsn,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    logger.info("members/rsn: user {} linked RSN {!r}", discord_user_id, rsn)
    return {"rsn": rsn}


@router.get("/me/feed")
async def member_feed(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
) -> list[dict]:
    """Return a personal activity feed for the authenticated user, keyed by their linked RSN."""
    discord_user_id = int(current_user["sub"])
    user_doc = await db["users"].find_one({"discord_user_id": discord_user_id}, {"rsn": 1})
    rsn = user_doc.get("rsn") if user_doc else None
    if not rsn:
        return []

    items: list[dict] = []

    async for doc in (
        db["loot_events"]
        .find({"player_name": rsn}, {"item_name": 1, "coin_value": 1, "source": 1, "timestamp": 1, "_id": 0})
        .sort("timestamp", -1).limit(limit)
    ):
        items.append({"type": "drop", "timestamp": doc["timestamp"].isoformat(),
                       "label": doc["item_name"], "detail": doc.get("source"), "value": doc.get("coin_value", 0)})

    async for doc in (
        db["level_events"]
        .find({"player_name": rsn}, {"skill": 1, "new_level": 1, "timestamp": 1, "_id": 0})
        .sort("timestamp", -1).limit(limit)
    ):
        items.append({"type": "level", "timestamp": doc["timestamp"].isoformat(),
                       "label": doc["skill"], "detail": None, "value": doc.get("new_level", 0)})

    async for doc in (
        db["xp_events"]
        .find({"player_name": rsn}, {"skill": 1, "xp": 1, "timestamp": 1, "_id": 0})
        .sort("timestamp", -1).limit(limit)
    ):
        items.append({"type": "xp_milestone", "timestamp": doc["timestamp"].isoformat(),
                       "label": doc["skill"], "detail": None, "value": doc.get("xp", 0)})

    async for doc in (
        db["achievement_events"]
        .find({"player_name": rsn}, {"achievement_type": 1, "name": 1, "timestamp": 1, "_id": 0})
        .sort("timestamp", -1).limit(limit)
    ):
        items.append({"type": doc.get("achievement_type", "quest"), "timestamp": doc["timestamp"].isoformat(),
                       "label": doc["name"], "detail": None, "value": None})

    async for doc in (
        db["pet_events"]
        .find({"player_name": rsn}, {"raw_message": 1, "timestamp": 1, "_id": 0})
        .sort("timestamp", -1).limit(limit)
    ):
        items.append({"type": "pet", "timestamp": doc["timestamp"].isoformat(),
                       "label": "Pet drop!", "detail": None, "value": None})

    async for doc in (
        db["collection_log_events"]
        .find({"player_name": rsn}, {"item_name": 1, "log_slots": 1, "log_slots_max": 1, "timestamp": 1, "_id": 0})
        .sort("timestamp", -1).limit(limit)
    ):
        items.append({"type": "collection_log", "timestamp": doc["timestamp"].isoformat(),
                       "label": doc["item_name"],
                       "detail": f"Slot {doc.get('log_slots')}/{doc.get('log_slots_max')}",
                       "value": None})

    async for doc in (
        db["clue_events"]
        .find({"player_name": rsn}, {"item_name": 1, "coin_value": 1, "timestamp": 1, "_id": 0})
        .sort("timestamp", -1).limit(limit)
    ):
        items.append({"type": "clue", "timestamp": doc["timestamp"].isoformat(),
                       "label": doc["item_name"], "detail": "Clue scroll", "value": doc.get("coin_value", 0)})

    async for doc in (
        db["pk_events"]
        .find({"$or": [{"winner": rsn}, {"loser": rsn}]},
              {"winner": 1, "loser": 1, "gp_exchanged": 1, "timestamp": 1, "_id": 0})
        .sort("timestamp", -1).limit(limit)
    ):
        won = doc.get("winner") == rsn
        items.append({"type": "pk", "timestamp": doc["timestamp"].isoformat(),
                       "label": f"{'Killed' if won else 'Killed by'} {doc['loser'] if won else doc['winner']}",
                       "detail": None, "value": doc.get("gp_exchanged", 0)})

    async for doc in (
        db["personal_best_events"]
        .find({"player_name": rsn}, {"activity": 1, "time_seconds": 1, "variant": 1, "timestamp": 1, "_id": 0})
        .sort("timestamp", -1).limit(limit)
    ):
        items.append({"type": "personal_best", "timestamp": doc["timestamp"].isoformat(),
                       "label": doc["activity"], "detail": doc.get("variant"), "value": doc.get("time_seconds")})

    async for doc in (
        db["hcim_death_events"]
        .find({"player_name": rsn}, {"timestamp": 1, "_id": 0})
        .sort("timestamp", -1).limit(limit)
    ):
        items.append({"type": "hcim_death", "timestamp": doc["timestamp"].isoformat(),
                       "label": "Died as HCIM", "detail": None, "value": None})

    items.sort(key=lambda x: x["timestamp"], reverse=True)
    return items[:limit]
