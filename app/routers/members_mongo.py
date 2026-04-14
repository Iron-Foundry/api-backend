# DEPRECATED — MongoDB implementation. Kept for reference. Not imported in production.
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

    now = datetime.now(timezone.utc)
    await db["users"].update_one(
        {"discord_user_id": discord_user_id},
        {"$set": {"rsn": rsn, "updated_at": now}},
    )
    logger.info("members/rsn: user {} linked RSN {!r}", discord_user_id, rsn)

    # ── Backfill from spread collections ───────────────────────────────────
    user_doc = await db["users"].find_one(
        {"discord_user_id": discord_user_id}, {"clan_rank": 1}
    )
    backfill: dict = {}

    # clan_rank — from most recent event if not already set
    if not user_doc or not user_doc.get("clan_rank"):
        for col in ("loot_events", "level_events", "xp_events", "achievement_events"):
            event = await db[col].find_one(
                {"player_name": rsn, "rank": {"$exists": True, "$ne": None}},
                {"rank": 1},
                sort=[("timestamp", -1)],
            )
            if event and event.get("rank"):
                backfill["clan_rank"] = event["rank"]
                logger.info(
                    "members/rsn: backfilled clan_rank={!r} for user {} from {}",
                    event["rank"], discord_user_id, col,
                )
                break

    # loot total — from loot_totals aggregate per player
    loot_doc = await db["loot_totals"].find_one(
        {"player_name": rsn}, {"total_value": 1, "_id": 0}
    )
    if loot_doc:
        backfill["total_loot_value"] = loot_doc["total_value"]

    # collection log slots — player's current max from collection_log_counts
    cl_doc = await db["collection_log_counts"].find_one(
        {"player_name": rsn}, {"log_slots": 1, "_id": 0}
    )
    if cl_doc:
        backfill["collection_log_slots"] = cl_doc["log_slots"]

    # ticket_ids — re-sync from tickets collection (keyed by Discord user ID)
    ticket_ids: list[int] = []
    async for doc in db["tickets"].find(
        {"creator.id": discord_user_id}, {"ticket_id": 1, "_id": 0}
    ):
        if isinstance(doc.get("ticket_id"), int):
            ticket_ids.append(doc["ticket_id"])
    if ticket_ids:
        backfill["ticket_ids"] = sorted(ticket_ids)

    if backfill:
        backfill["updated_at"] = now
        await db["users"].update_one(
            {"discord_user_id": discord_user_id},
            {"$set": backfill},
        )
        logger.info(
            "members/rsn: backfilled fields {} for user {}",
            list(backfill.keys()), discord_user_id,
        )

    return {"rsn": rsn}


@router.get("/me/feed")
async def member_feed(
    limit: int = Query(default=100, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
) -> list[dict]:
    """Return a personal activity feed for the authenticated user, keyed by their linked RSN.

    All event types are included with no value filters. The `limit` most recent
    events across all collections are returned, sorted by timestamp descending.
    """
    discord_user_id = int(current_user["sub"])
    user_doc = await db["users"].find_one({"discord_user_id": discord_user_id}, {"rsn": 1})
    rsn = user_doc.get("rsn") if user_doc else None
    if not rsn:
        return []

    # Per-collection fetch limit — generous so the global merge isn't skewed
    # toward event types the player happens to have many of.
    per_col = min(limit * 2, 500)
    items: list[dict] = []

    async for doc in (
        db["loot_events"]
        .find({"player_name": rsn}, {"item_name": 1, "coin_value": 1, "source": 1, "timestamp": 1, "_id": 0})
        .sort("timestamp", -1).limit(per_col)
    ):
        items.append({"type": "drop", "timestamp": doc["timestamp"].isoformat(),
                       "label": doc["item_name"], "detail": doc.get("source"), "value": doc.get("coin_value", 0)})

    async for doc in (
        db["level_events"]
        .find({"player_name": rsn}, {"skill": 1, "new_level": 1, "timestamp": 1, "_id": 0})
        .sort("timestamp", -1).limit(per_col)
    ):
        skill = doc["skill"]
        items.append({"type": "level", "timestamp": doc["timestamp"].isoformat(),
                       "label": "Total Level" if skill == "total" else skill,
                       "detail": None, "value": doc.get("new_level", 0)})

    async for doc in (
        db["xp_events"]
        .find({"player_name": rsn}, {"skill": 1, "xp": 1, "timestamp": 1, "_id": 0})
        .sort("timestamp", -1).limit(per_col)
    ):
        items.append({"type": "xp_milestone", "timestamp": doc["timestamp"].isoformat(),
                       "label": doc["skill"], "detail": None, "value": doc.get("xp", 0)})

    async for doc in (
        db["achievement_events"]
        .find({"player_name": rsn}, {"achievement_type": 1, "name": 1, "timestamp": 1, "_id": 0})
        .sort("timestamp", -1).limit(per_col)
    ):
        items.append({"type": doc.get("achievement_type", "quest"), "timestamp": doc["timestamp"].isoformat(),
                       "label": doc["name"], "detail": None, "value": None})

    async for doc in (
        db["pet_events"]
        .find({"player_name": rsn}, {"raw_message": 1, "timestamp": 1, "_id": 0})
        .sort("timestamp", -1).limit(per_col)
    ):
        items.append({"type": "pet", "timestamp": doc["timestamp"].isoformat(),
                       "label": "Pet drop!", "detail": None, "value": None})

    async for doc in (
        db["collection_log_events"]
        .find({"player_name": rsn}, {"item_name": 1, "log_slots": 1, "log_slots_max": 1, "timestamp": 1, "_id": 0})
        .sort("timestamp", -1).limit(per_col)
    ):
        items.append({"type": "collection_log", "timestamp": doc["timestamp"].isoformat(),
                       "label": doc["item_name"],
                       "detail": f"Slot {doc.get('log_slots')}/{doc.get('log_slots_max')}",
                       "value": None})

    async for doc in (
        db["clue_events"]
        .find({"player_name": rsn}, {"item_name": 1, "coin_value": 1, "timestamp": 1, "_id": 0})
        .sort("timestamp", -1).limit(per_col)
    ):
        items.append({"type": "clue", "timestamp": doc["timestamp"].isoformat(),
                       "label": doc["item_name"], "detail": "Clue scroll", "value": doc.get("coin_value", 0)})

    async for doc in (
        db["pk_events"]
        .find({"$or": [{"winner": rsn}, {"loser": rsn}]},
              {"winner": 1, "loser": 1, "gp_exchanged": 1, "timestamp": 1, "_id": 0})
        .sort("timestamp", -1).limit(per_col)
    ):
        won = doc.get("winner") == rsn
        items.append({"type": "pk", "timestamp": doc["timestamp"].isoformat(),
                       "label": f"{'Killed' if won else 'Killed by'} {doc['loser'] if won else doc['winner']}",
                       "detail": None, "value": doc.get("gp_exchanged", 0)})

    async for doc in (
        db["personal_best_events"]
        .find({"player_name": rsn}, {"activity": 1, "time_seconds": 1, "variant": 1, "timestamp": 1, "_id": 0})
        .sort("timestamp", -1).limit(per_col)
    ):
        items.append({"type": "personal_best", "timestamp": doc["timestamp"].isoformat(),
                       "label": doc["activity"], "detail": doc.get("variant"), "value": doc.get("time_seconds")})

    async for doc in (
        db["hcim_death_events"]
        .find({"player_name": rsn}, {"timestamp": 1, "_id": 0})
        .sort("timestamp", -1).limit(per_col)
    ):
        items.append({"type": "hcim_death", "timestamp": doc["timestamp"].isoformat(),
                       "label": "Died as HCIM", "detail": None, "value": None})

    async for doc in (
        db["loot_key_events"]
        .find({"player_name": rsn}, {"coin_value": 1, "timestamp": 1, "_id": 0})
        .sort("timestamp", -1).limit(per_col)
    ):
        items.append({"type": "loot_key", "timestamp": doc["timestamp"].isoformat(),
                       "label": "Loot key opened", "detail": None, "value": doc.get("coin_value", 0)})

    async for doc in (
        db["coffer_events"]
        .find({"player_name": rsn}, {"amount": 1, "is_donation": 1, "timestamp": 1, "_id": 0})
        .sort("timestamp", -1).limit(per_col)
    ):
        is_donation = doc.get("is_donation", True)
        items.append({"type": "coffer", "timestamp": doc["timestamp"].isoformat(),
                       "label": "Coffer donation" if is_donation else "Coffer withdrawal",
                       "detail": None, "value": doc.get("amount", 0)})

    items.sort(key=lambda x: x["timestamp"], reverse=True)
    return items[:limit]


@router.get("/me/tickets")
async def member_tickets(
    current_user: dict = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
) -> list[dict]:
    """Return all tickets created by the authenticated user."""
    discord_user_id = int(current_user["sub"])
    tickets: list[dict] = []
    async for doc in (
        db["tickets"]
        .find(
            {"creator.id": discord_user_id},
            {"_id": 0, "staff_note": 0, "channel_id": 0, "guild_id": 0,
             "panel_message_id": 0, "participants": 0, "assigned_staff": 0},
        )
        .sort("ticket_id", -1)
    ):
        # Convert datetime fields to ISO strings for JSON serialisation.
        for field in ("created_at", "closed_at", "last_message_at"):
            if doc.get(field) is not None and hasattr(doc[field], "isoformat"):
                doc[field] = doc[field].isoformat()
        tickets.append(doc)
    return tickets


@router.get("/me/tickets/{ticket_id}/transcript")
async def member_ticket_transcript(
    ticket_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
) -> dict:
    """Return the transcript for one of the authenticated user's tickets.

    The staff_note field is never returned. Returns 404 if the ticket doesn't
    belong to this user or has no transcript (e.g. sensitive ticket types).
    """
    discord_user_id = int(current_user["sub"])

    ticket = await db["tickets"].find_one(
        {"ticket_id": ticket_id, "creator.id": discord_user_id}, {"_id": 0}
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    doc = await db["transcripts"].find_one(
        {"ticket_id": ticket_id}, {"_id": 0, "staff_note": 0}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Transcript not available for this ticket.")

    # Recursively convert datetime objects to ISO strings.
    def _iso(obj: object) -> object:
        if hasattr(obj, "isoformat"):
            return obj.isoformat()  # type: ignore[union-attr]
        if isinstance(obj, dict):
            return {k: _iso(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_iso(i) for i in obj]
        return obj

    return _iso(doc)  # type: ignore[return-value]
