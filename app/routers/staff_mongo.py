# DEPRECATED — MongoDB implementation. Kept for reference. Not imported in production.
"""Staff router — rank-protected endpoints for staff-only operations."""

from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.asynchronous.database import AsyncDatabase

from app.dependencies import get_current_user, get_db

router = APIRouter(prefix="/staff", tags=["staff"])

_DISCORD_ROLE_ORDER = [
    "Guest", "Achiever", "Sapphire", "Emerald", "Ruby",
    "Diamond", "Dragonstone", "Onyx", "Zenyte",
    "Ex-Moderator", "Mentor", "Event Team", "Moderator",
    "Senior Moderator", "Deputy Owner", "Co-owner",
]

# Ticket types grouped by the minimum Discord role required to view them.
_TICKET_TYPE_MIN_RANK: dict[str, str] = {
    "contact_mentor":   "Mentor",
    "general":          "Moderator",
    "rankup":           "Moderator",
    "join_cc":          "Moderator",
    "apply_staff":      "Senior Moderator",
    "apply_mentor":     "Senior Moderator",
    "apply_event_team": "Senior Moderator",
    "sensitive":        "Senior Moderator",
    "survey":           "Senior Moderator",
}


def _has_min_rank(discord_roles: list[str], min_role: str) -> bool:
    try:
        min_idx = _DISCORD_ROLE_ORDER.index(min_role)
    except ValueError:
        return False
    for role in discord_roles:
        if role in _DISCORD_ROLE_ORDER and _DISCORD_ROLE_ORDER.index(role) >= min_idx:
            return True
    return False


def _allowed_ticket_types(discord_roles: list[str]) -> list[str]:
    """Return ticket type identifiers the caller is authorised to view."""
    return [t for t, min_r in _TICKET_TYPE_MIN_RANK.items() if _has_min_rank(discord_roles, min_r)]


async def _get_roles(current_user: dict, db: AsyncDatabase) -> list[str]:
    discord_user_id = int(current_user["sub"])
    doc = await db["users"].find_one(
        {"discord_user_id": discord_user_id}, {"discord_roles": 1}
    )
    return doc.get("discord_roles", []) if doc else []


async def _require_rank(min_role: str, current_user: dict, db: AsyncDatabase) -> None:
    """Raise HTTP 403 if the user doesn't hold at least min_role."""
    roles = await _get_roles(current_user, db)
    if not _has_min_rank(roles, min_role):
        raise HTTPException(status_code=403, detail=f"Requires {min_role} or higher.")


def _iso(obj: object) -> object:
    """Recursively convert datetime objects to ISO strings for JSON serialisation."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _iso(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_iso(i) for i in obj]
    return obj


# ── Endpoints ──────────────────────────────────────────────────────────────


@router.get("/overview")
async def staff_overview(
    current_user: dict = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
) -> dict:
    """High-level clan stats. Requires Mentor or higher."""
    await _require_rank("Mentor", current_user, db)
    total_members, open_tickets, total_tickets = await asyncio.gather(
        db["users"].count_documents({}),
        db["tickets"].count_documents({"status": "open"}),
        db["tickets"].count_documents({}),
    )
    return {
        "total_members": total_members,
        "open_tickets": open_tickets,
        "total_tickets": total_tickets,
    }


@router.get("/members")
async def staff_members(
    current_user: dict = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
) -> list[dict]:
    """Return all member profiles. Requires Moderator or higher."""
    await _require_rank("Moderator", current_user, db)
    members: list[dict] = []
    async for doc in db["users"].find(
        {},
        {
            "_id": 0,
            "discord_user_id": 1,
            "discord_username": 1,
            "rsn": 1,
            "clan_rank": 1,
            "discord_roles": 1,
            "stats_opt_out": 1,
            "created_at": 1,
            "total_loot_value": 1,
            "collection_log_slots": 1,
        },
    ).sort("created_at", -1):
        members.append(_iso(doc))
    return members


@router.get("/tickets")
async def staff_tickets(
    limit: int = Query(default=50, ge=1, le=200),
    skip: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
) -> list[dict]:
    """Return tickets visible to the caller based on their rank."""
    roles = await _get_roles(current_user, db)
    if not _has_min_rank(roles, "Mentor"):
        raise HTTPException(status_code=403, detail="Requires Mentor or higher.")
    allowed = _allowed_ticket_types(roles)
    if not allowed:
        return []
    query: dict = {"ticket_type": {"$in": allowed}}
    if status:
        query["status"] = status
    tickets: list[dict] = []
    async for doc in (
        db["tickets"]
        .find(query, {"_id": 0})
        .sort("ticket_id", -1)
        .skip(skip)
        .limit(limit)
    ):
        tickets.append(_iso(doc))
    return tickets


@router.get("/tickets/{ticket_id}/transcript")
async def staff_ticket_transcript(
    ticket_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
) -> dict:
    """Return the full transcript for a ticket the caller is authorised to view."""
    roles = await _get_roles(current_user, db)
    if not _has_min_rank(roles, "Mentor"):
        raise HTTPException(status_code=403, detail="Requires Mentor or higher.")
    allowed = _allowed_ticket_types(roles)
    # Verify ticket exists and caller may access its type.
    ticket = await db["tickets"].find_one(
        {"ticket_id": ticket_id, "ticket_type": {"$in": allowed}}, {"ticket_type": 1}
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found or access denied.")
    doc = await db["transcripts"].find_one({"ticket_id": ticket_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Transcript not available.")
    return _iso(doc)  # type: ignore[return-value]
