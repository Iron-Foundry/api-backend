"""Members router — authenticated endpoints for profile self-management."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Event, Ticket, User
from app.dependencies import get_current_user, get_session

router = APIRouter(prefix="/members", tags=["members"])

_RSN_RE = re.compile(r"^[A-Za-z0-9 _-]{1,12}$")


# ── request bodies ─────────────────────────────────────────────────────────


class PrivacyUpdate(BaseModel):
    stats_opt_out: bool | None = None
    hide_presence_notifications: bool | None = None


class RsnUpdate(BaseModel):
    rsn: str


# ── endpoints ──────────────────────────────────────────────────────────────


@router.patch("/me/privacy")
async def update_privacy(
    body: PrivacyUpdate,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Toggle stats opt-out for the authenticated user."""
    discord_user_id = int(current_user["sub"])
    values: dict = {"updated_at": datetime.now(timezone.utc)}
    if body.stats_opt_out is not None:
        values["stats_opt_out"] = body.stats_opt_out
    if body.hide_presence_notifications is not None:
        values["hide_presence_notifications"] = body.hide_presence_notifications
    if len(values) == 1:
        return {}
    await session.execute(
        update(User).where(User.discord_user_id == discord_user_id).values(**values)
    )
    await session.commit()
    logger.info("members/privacy: user {} updated privacy {}", discord_user_id, values)
    return {k: v for k, v in values.items() if k != "updated_at"}


@router.patch("/me/rsn")
async def update_rsn(
    body: RsnUpdate,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
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
    existing_result = await session.execute(
        select(User.discord_user_id).where(
            func.lower(User.rsn) == rsn.lower()
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing and existing != discord_user_id:
        raise HTTPException(status_code=409, detail="That RSN is linked to another account.")

    now = datetime.now(timezone.utc)
    await session.execute(
        update(User)
        .where(User.discord_user_id == discord_user_id)
        .values(rsn=rsn, updated_at=now)
    )
    logger.info("members/rsn: user {} linked RSN {!r}", discord_user_id, rsn)

    # ── Backfill from events table ──────────────────────────────────────────
    user_result = await session.execute(
        select(User.clan_rank, User.total_loot_value, User.collection_log_slots)
        .where(User.discord_user_id == discord_user_id)
    )
    user_row = user_result.one_or_none()
    backfill: dict = {}

    # clan_rank — from most recent event if not already set
    if not user_row or not user_row.clan_rank:
        rank_result = await session.execute(
            select(Event.data["rank"].as_string())
            .where(
                func.lower(Event.player_name) == rsn.lower(),
                Event.data["rank"].as_string().isnot(None),
                Event.type.in_(["loot", "level", "xp_milestone", "quest", "diary", "combat_achievement"]),
            )
            .order_by(Event.timestamp.desc())
            .limit(1)
        )
        rank_val = rank_result.scalar_one_or_none()
        if rank_val:
            backfill["clan_rank"] = rank_val
            logger.info(
                "members/rsn: backfilled clan_rank={!r} for user {}",
                rank_val,
                discord_user_id,
            )

    # total_loot_value — sum of loot/loot_key/clue_item coin_value from events
    if not user_row or user_row.total_loot_value == 0:
        loot_result = await session.execute(
            select(
                func.coalesce(
                    func.sum(Event.data["coin_value"].as_integer()), 0
                )
            ).where(
                func.lower(Event.player_name) == rsn.lower(),
                Event.type.in_(["loot", "loot_key", "clue_item"]),
            )
        )
        total_loot = loot_result.scalar_one_or_none() or 0
        if total_loot:
            backfill["total_loot_value"] = total_loot

    # collection_log_slots — max slots from events
    if not user_row or user_row.collection_log_slots == 0:
        cl_result = await session.execute(
            select(
                func.coalesce(func.max(Event.data["log_slots"].as_integer()), 0)
            ).where(
                func.lower(Event.player_name) == rsn.lower(),
                Event.type == "collection_log",
            )
        )
        cl_slots = cl_result.scalar_one_or_none() or 0
        if cl_slots:
            backfill["collection_log_slots"] = cl_slots

    # ticket_ids — sync from tickets table
    ticket_result = await session.execute(
        select(Ticket.ticket_id).where(Ticket.creator_id == discord_user_id)
    )
    ticket_ids = sorted([row[0] for row in ticket_result])
    if ticket_ids:
        backfill["ticket_ids"] = ticket_ids

    if backfill:
        backfill["updated_at"] = now
        await session.execute(
            update(User)
            .where(User.discord_user_id == discord_user_id)
            .values(**backfill)
        )
        logger.info(
            "members/rsn: backfilled fields {} for user {}",
            list(backfill.keys()),
            discord_user_id,
        )

    # Stamp user_id on all events whose player_name matches this RSN
    event_result = await session.execute(
        update(Event)
        .where(func.lower(Event.player_name) == rsn.lower())
        .values(user_id=discord_user_id)
    )
    logger.info(
        "members/rsn: linked user_id {} to {} event rows",
        discord_user_id,
        event_result.rowcount,
    )

    await session.commit()
    return {"rsn": rsn}


@router.get("/me/feed")
async def member_feed(
    limit: int = Query(default=100, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Return a personal activity feed for the authenticated user, keyed by their linked RSN.

    All event types are included with no value filters. The `limit` most recent
    events across all collections are returned, sorted by timestamp descending.
    """
    discord_user_id = int(current_user["sub"])
    user_result = await session.execute(
        select(User.rsn).where(User.discord_user_id == discord_user_id)
    )
    rsn = user_result.scalar_one_or_none()
    if not rsn:
        return []

    fetch_limit = min(limit * 10, 2000)
    events_result = await session.execute(
        select(Event)
        .where(
            Event.user_id == discord_user_id,
            Event.type.notin_(["unknown"]),
        )
        .order_by(Event.timestamp.desc())
        .limit(fetch_limit)
    )
    rows = events_result.scalars().all()

    # Also fetch PK events where player is the loser
    pk_result = await session.execute(
        select(Event)
        .where(
            Event.type == "pk",
            Event.data["loser"].as_string() == rsn,
            Event.user_id != discord_user_id,
        )
        .order_by(Event.timestamp.desc())
        .limit(fetch_limit)
    )
    pk_rows = pk_result.scalars().all()

    all_rows = list(rows) + list(pk_rows)

    items: list[dict] = []
    for row in all_rows:
        d = row.data or {}
        ts = row.timestamp.isoformat()
        t = row.type

        if t == "loot":
            items.append({"type": "drop", "timestamp": ts,
                          "label": d.get("item_name", ""),
                          "detail": d.get("source"), "value": d.get("coin_value", 0)})
        elif t == "level":
            skill = d.get("skill", "")
            items.append({"type": "level", "timestamp": ts,
                          "label": "Total Level" if skill == "total" else skill,
                          "detail": None, "value": d.get("new_level", 0)})
        elif t == "xp_milestone":
            items.append({"type": "xp_milestone", "timestamp": ts,
                          "label": d.get("skill", ""), "detail": None, "value": d.get("xp", 0)})
        elif t in ("quest", "diary", "combat_achievement"):
            items.append({"type": d.get("achievement_type", t), "timestamp": ts,
                          "label": d.get("name", ""), "detail": None, "value": None})
        elif t == "pet":
            items.append({"type": "pet", "timestamp": ts,
                          "label": "Pet drop!", "detail": None, "value": None})
        elif t == "collection_log":
            items.append({"type": "collection_log", "timestamp": ts,
                          "label": d.get("item_name", ""),
                          "detail": f"Slot {d.get('log_slots')}/{d.get('log_slots_max')}",
                          "value": None})
        elif t == "clue_item":
            items.append({"type": "clue", "timestamp": ts,
                          "label": d.get("item_name", ""), "detail": "Clue scroll",
                          "value": d.get("coin_value", 0)})
        elif t == "pk":
            won = row.user_id == discord_user_id and (row.player_name or "").lower() == rsn.lower()
            other = d.get("loser" if won else "winner", "")
            items.append({"type": "pk", "timestamp": ts,
                          "label": f"{'Killed' if won else 'Killed by'} {other}",
                          "detail": None, "value": d.get("gp_exchanged", 0)})
        elif t == "personal_best":
            items.append({"type": "personal_best", "timestamp": ts,
                          "label": d.get("activity", ""), "detail": d.get("variant"),
                          "value": d.get("time_seconds")})
        elif t == "hcim_death":
            items.append({"type": "hcim_death", "timestamp": ts,
                          "label": "Died as HCIM", "detail": None, "value": None})
        elif t == "loot_key":
            items.append({"type": "loot_key", "timestamp": ts,
                          "label": "Loot key opened", "detail": None,
                          "value": d.get("coin_value", 0)})
        else:
            items.append({"type": t, "timestamp": ts,
                          "label": d.get("name") or d.get("item_name") or t,
                          "detail": None, "value": None})

    items.sort(key=lambda x: x["timestamp"], reverse=True)
    return items[:limit]


@router.get("/me/tickets")
async def member_tickets(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Return all tickets created by the authenticated user."""
    discord_user_id = int(current_user["sub"])
    result = await session.execute(
        select(Ticket)
        .where(Ticket.creator_id == discord_user_id)
        .order_by(Ticket.ticket_id.desc())
    )
    tickets: list[dict] = []
    for row in result.scalars():
        tickets.append({
            "ticket_id": row.ticket_id,
            "ticket_type": row.ticket_type,
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "closed_at": row.closed_at.isoformat() if row.closed_at else None,
            "last_message_at": row.last_message_at.isoformat() if row.last_message_at else None,
            "close_reason": row.close_reason,
        })
    return tickets


@router.get("/me/tickets/{ticket_id}/transcript")
async def member_ticket_transcript(
    ticket_id: int,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return the transcript for one of the authenticated user's tickets.

    The staff_note field is never returned. Returns 404 if the ticket doesn't
    belong to this user or has no transcript (e.g. sensitive ticket types).
    """
    from app.db.models import Transcript

    discord_user_id = int(current_user["sub"])

    ticket_result = await session.execute(
        select(Ticket.ticket_id).where(
            Ticket.ticket_id == ticket_id,
            Ticket.creator_id == discord_user_id,
        )
    )
    if not ticket_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Ticket not found.")

    tr_result = await session.execute(
        select(Transcript).where(Transcript.ticket_id == ticket_id)
    )
    tr = tr_result.scalar_one_or_none()
    if not tr:
        raise HTTPException(
            status_code=404, detail="Transcript not available for this ticket."
        )

    return {"ticket_id": tr.ticket_id, "entries": tr.entries}
