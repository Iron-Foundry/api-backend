"""Staff router — rank-protected endpoints for staff-only operations."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CofferEvent, Event, Leaderboard, MembershipEvent, Ticket, Transcript, User
from app.dependencies import get_current_user, get_session

_RSN_RE = re.compile(r"^[A-Za-z0-9 _-]{1,12}$")

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


async def _get_roles(current_user: dict, session: AsyncSession) -> list[str]:
    discord_user_id = int(current_user["sub"])
    result = await session.execute(
        select(User.discord_roles).where(User.discord_user_id == discord_user_id)
    )
    roles = result.scalar_one_or_none()
    return roles or []


async def _require_rank(
    min_role: str, current_user: dict, session: AsyncSession
) -> None:
    """Raise HTTP 403 if the user doesn't hold at least min_role."""
    roles = await _get_roles(current_user, session)
    if not _has_min_rank(roles, min_role):
        raise HTTPException(status_code=403, detail=f"Requires {min_role} or higher.")


# ── Endpoints ──────────────────────────────────────────────────────────────


@router.get("/overview")
async def staff_overview(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """High-level clan stats. Requires Mentor or higher."""
    await _require_rank("Mentor", current_user, session)

    total_members = (await session.execute(select(func.count()).select_from(User))).scalar_one()
    open_tickets = (
        await session.execute(
            select(func.count()).select_from(Ticket).where(Ticket.status == "open")
        )
    ).scalar_one()
    total_tickets = (
        await session.execute(select(func.count()).select_from(Ticket))
    ).scalar_one()

    return {
        "total_members": total_members,
        "open_tickets": open_tickets,
        "total_tickets": total_tickets,
    }


@router.get("/members")
async def staff_members(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    search: str | None = None,
) -> list[dict]:
    """Return all member profiles. Requires Moderator or higher."""
    await _require_rank("Moderator", current_user, session)
    stmt = select(
        User.discord_user_id,
        User.discord_username,
        User.discord_avatar_url,
        User.rsn,
        User.clan_rank,
        User.discord_roles,
        User.stats_opt_out,
        User.join_date,
        User.created_at,
        User.total_loot_value,
        User.collection_log_slots,
        User.recruited_by,
        User.key_is_active,
    )
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            User.rsn.ilike(pattern) | User.discord_username.ilike(pattern)
        )
    stmt = stmt.order_by(User.join_date.asc().nulls_last())
    result = await session.execute(stmt)
    members: list[dict] = []
    for row in result:
        members.append({
            "discord_user_id": str(row.discord_user_id),
            "discord_username": row.discord_username,
            "discord_avatar_url": row.discord_avatar_url,
            "rsn": row.rsn,
            "clan_rank": row.clan_rank,
            "discord_roles": row.discord_roles,
            "stats_opt_out": row.stats_opt_out,
            "join_date": row.join_date.isoformat() if row.join_date else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "total_loot_value": row.total_loot_value,
            "collection_log_slots": row.collection_log_slots,
            "recruited_by": str(row.recruited_by) if row.recruited_by else None,
            "key_is_active": row.key_is_active,
        })
    return members


class RsnUpdate(BaseModel):
    rsn: str | None


@router.patch("/members/{discord_user_id}/rsn")
async def update_member_rsn(
    discord_user_id: int,
    body: RsnUpdate,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Set, change, or clear a member's RSN. Requires Moderator or higher.

    Performs the same backfill and event-linking as the self-service
    PATCH /members/me/rsn endpoint. When the user already has an RSN the
    old name is cascaded across all player_name columns before the new one
    is applied.
    """
    await _require_rank("Moderator", current_user, session)

    new_rsn = body.rsn.strip() if body.rsn else None
    if new_rsn == "":
        new_rsn = None

    # validate format when setting a value
    if new_rsn and not _RSN_RE.match(new_rsn):
        raise HTTPException(
            status_code=422,
            detail="RSN must be 1–12 characters: letters, numbers, spaces, hyphens, underscores.",
        )

    # fetch current state for this user
    user_result = await session.execute(
        select(
            User.discord_user_id,
            User.rsn,
            User.clan_rank,
            User.total_loot_value,
            User.collection_log_slots,
        ).where(User.discord_user_id == discord_user_id)
    )
    user_row = user_result.one_or_none()
    if not user_row:
        raise HTTPException(status_code=404, detail="Member not found.")

    old_rsn: str | None = user_row.rsn
    now = datetime.now(timezone.utc)

    # ── Clearing the RSN ──────────────────────────────────────────────────
    if new_rsn is None:
        await session.execute(
            update(User)
            .where(User.discord_user_id == discord_user_id)
            .values(rsn=None, updated_at=now)
        )
        if old_rsn:
            # unlink events that were linked via this RSN
            await session.execute(
                update(Event)
                .where(
                    Event.user_id == discord_user_id,
                    func.lower(Event.player_name) == old_rsn.lower(),
                )
                .values(user_id=None)
            )
        await session.commit()
        logger.info("staff/rsn: cleared RSN for user {}", discord_user_id)
        return {"discord_user_id": str(discord_user_id), "rsn": None}

    # ── Setting / changing the RSN ────────────────────────────────────────
    # check uniqueness (case-insensitive, excluding self)
    conflict = await session.execute(
        select(User.discord_user_id).where(
            func.lower(User.rsn) == new_rsn.lower(),
            User.discord_user_id != discord_user_id,
        )
    )
    if conflict.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="RSN already linked to another account.")

    # if this is a rename, cascade old_rsn → new_rsn across all tables
    if old_rsn and old_rsn.lower() != new_rsn.lower():
        await session.execute(
            update(Event)
            .where(func.lower(Event.player_name) == old_rsn.lower())
            .values(player_name=new_rsn)
        )
        await session.execute(
            text(
                "UPDATE events SET data = jsonb_set(data, '{winner}', to_jsonb(:new::text))"
                " WHERE type = 'pk' AND lower(data->>'winner') = lower(:old)"
            ),
            {"old": old_rsn, "new": new_rsn},
        )
        await session.execute(
            text(
                "UPDATE events SET data = jsonb_set(data, '{loser}', to_jsonb(:new::text))"
                " WHERE type = 'pk' AND lower(data->>'loser') = lower(:old)"
            ),
            {"old": old_rsn, "new": new_rsn},
        )
        await session.execute(
            update(CofferEvent)
            .where(func.lower(CofferEvent.player_name) == old_rsn.lower())
            .values(player_name=new_rsn)
        )
        await session.execute(
            update(MembershipEvent)
            .where(func.lower(MembershipEvent.player_name) == old_rsn.lower())
            .values(player_name=new_rsn)
        )
        await session.execute(
            update(Leaderboard)
            .where(func.lower(Leaderboard.player_name) == old_rsn.lower())
            .values(player_name=new_rsn)
        )
        logger.info(
            "staff/rsn: cascaded rename {!r} → {!r} for user {}",
            old_rsn, new_rsn, discord_user_id,
        )

    # update the RSN on the user record
    await session.execute(
        update(User)
        .where(User.discord_user_id == discord_user_id)
        .values(rsn=new_rsn, updated_at=now)
    )
    logger.info("staff/rsn: user {} set RSN {!r}", discord_user_id, new_rsn)

    # ── Backfill (same as self-service endpoint) ──────────────────────────
    backfill: dict = {}

    if not user_row.clan_rank:
        rank_result = await session.execute(
            select(Event.data["rank"].as_string())
            .where(
                func.lower(Event.player_name) == new_rsn.lower(),
                Event.data["rank"].as_string().isnot(None),
                Event.type.in_(["loot", "level", "xp_milestone", "quest", "diary", "combat_achievement"]),
            )
            .order_by(Event.timestamp.desc())
            .limit(1)
        )
        rank_val = rank_result.scalar_one_or_none()
        if rank_val:
            backfill["clan_rank"] = rank_val

    if not user_row.total_loot_value:
        loot_result = await session.execute(
            select(func.coalesce(func.sum(Event.data["coin_value"].as_integer()), 0)).where(
                func.lower(Event.player_name) == new_rsn.lower(),
                Event.type.in_(["loot", "loot_key", "clue_item"]),
            )
        )
        total_loot = loot_result.scalar_one_or_none() or 0
        if total_loot:
            backfill["total_loot_value"] = total_loot

    if not user_row.collection_log_slots:
        cl_result = await session.execute(
            select(func.coalesce(func.max(Event.data["log_slots"].as_integer()), 0)).where(
                func.lower(Event.player_name) == new_rsn.lower(),
                Event.type == "collection_log",
            )
        )
        cl_slots = cl_result.scalar_one_or_none() or 0
        if cl_slots:
            backfill["collection_log_slots"] = cl_slots

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
            "staff/rsn: backfilled {} for user {}",
            list(backfill.keys()), discord_user_id,
        )

    # stamp user_id on all events matching the new RSN
    event_result = await session.execute(
        update(Event)
        .where(func.lower(Event.player_name) == new_rsn.lower())
        .values(user_id=discord_user_id)
    )
    logger.info(
        "staff/rsn: linked user_id {} to {} event rows",
        discord_user_id, event_result.rowcount,
    )

    await session.commit()
    return {"discord_user_id": discord_user_id, "rsn": new_rsn}


@router.get("/tickets")
async def staff_tickets(
    limit: int = Query(default=50, ge=1, le=200),
    skip: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Return tickets visible to the caller based on their rank."""
    roles = await _get_roles(current_user, session)
    if not _has_min_rank(roles, "Mentor"):
        raise HTTPException(status_code=403, detail="Requires Mentor or higher.")
    allowed = _allowed_ticket_types(roles)
    if not allowed:
        return []

    stmt = (
        select(Ticket)
        .where(Ticket.ticket_type.in_(allowed))
        .order_by(Ticket.ticket_id.desc())
        .offset(skip)
        .limit(limit)
    )
    if status:
        stmt = stmt.where(Ticket.status == status)

    result = await session.execute(stmt)
    tickets: list[dict] = []
    for row in result.scalars():
        tickets.append({
            "ticket_id": row.ticket_id,
            "guild_id": row.guild_id,
            "ticket_type": row.ticket_type,
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "closed_at": row.closed_at.isoformat() if row.closed_at else None,
            "last_message_at": row.last_message_at.isoformat() if row.last_message_at else None,
            "creator": {
                "id": row.creator_id,
                "display_name": row.creator_name,
                "avatar_url": None,
            },
            "closed_by_id": row.closed_by_id,
            "close_reason": row.close_reason,
            "staff_note": row.staff_note,
        })
    return tickets


@router.get("/tickets/{ticket_id}/transcript")
async def staff_ticket_transcript(
    ticket_id: int,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return the full transcript for a ticket the caller is authorised to view."""
    roles = await _get_roles(current_user, session)
    if not _has_min_rank(roles, "Mentor"):
        raise HTTPException(status_code=403, detail="Requires Mentor or higher.")
    allowed = _allowed_ticket_types(roles)

    ticket_result = await session.execute(
        select(Ticket.ticket_type).where(
            Ticket.ticket_id == ticket_id,
            Ticket.ticket_type.in_(allowed),
        )
    )
    if not ticket_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Ticket not found or access denied.")

    tr_result = await session.execute(
        select(Transcript).where(Transcript.ticket_id == ticket_id)
    )
    tr = tr_result.scalar_one_or_none()
    if not tr:
        raise HTTPException(status_code=404, detail="Transcript not available.")

    raw = tr.entries
    entries = raw.get("entries", []) if isinstance(raw, dict) else (raw or [])
    return {"ticket_id": tr.ticket_id, "entries": entries}
