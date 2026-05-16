"""Staff router - rank-protected endpoints for staff-only operations."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import func, select, text, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Event,
    Ticket,
    Transcript,
    User,
)
from app.dependencies import get_current_user, get_session
from app.services.page_permissions import check_page_permission, get_admin_bypass_roles
from app.services.rank_mappings import get_effective_roles, get_role_label_map
from app.services.rsn_cascade import backfill_user_from_rsn, cascade_rsn_change

_RSN_RE = re.compile(r"^[A-Za-z0-9 _-]{1,12}$")

router = APIRouter(prefix="/staff", tags=["staff"])

_DISCORD_ROLE_ORDER = [
    "Guest",
    "Achiever",
    "Sapphire",
    "Emerald",
    "Ruby",
    "Diamond",
    "Dragonstone",
    "Onyx",
    "Zenyte",
    "Ex-Moderator",
    "Foundry Mentors",
    "Event Team",
    "Moderator",
    "Senior Moderator",
    "Deputy Owner",
    "Co-owner",
]

_TICKET_TYPE_MIN_RANK: dict[str, str] = {
    "contact_mentor": "Foundry Mentors",
    "general": "Moderator",
    "rankup": "Moderator",
    "join_cc": "Moderator",
    "apply_staff": "Senior Moderator",
    "apply_mentor": "Senior Moderator",
    "apply_event_team": "Senior Moderator",
    "sensitive": "Senior Moderator",
    "survey": "Senior Moderator",
}


def _has_min_rank_by_label(role_labels: list[str], min_role: str) -> bool:
    """Check minimum rank using resolved label names."""
    try:
        min_idx = _DISCORD_ROLE_ORDER.index(min_role)
    except ValueError:
        return False
    for label in role_labels:
        if label in _DISCORD_ROLE_ORDER and _DISCORD_ROLE_ORDER.index(label) >= min_idx:
            return True
    return False


def _allowed_ticket_types(role_labels: list[str]) -> list[str]:
    """Return ticket type identifiers the caller is authorised to view (by resolved labels)."""
    return [
        t
        for t, min_r in _TICKET_TYPE_MIN_RANK.items()
        if _has_min_rank_by_label(role_labels, min_r)
    ]


async def _get_roles(current_user: dict, session: AsyncSession) -> list[str]:
    discord_user_id = int(current_user["sub"])
    return await get_effective_roles(discord_user_id, session)


async def _require_rank(
    page_id: str, action: str, current_user: dict, session: AsyncSession
) -> None:
    """Raise HTTP 403 if the user lacks page permission."""
    roles = await _get_roles(current_user, session)
    if not await check_page_permission(page_id, action, roles, session):
        raise HTTPException(status_code=403, detail="Permission denied.")


@router.get("/overview")
async def staff_overview(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """High-level clan stats. Requires Mentor or higher."""
    await _require_rank("staff.home", "read", current_user, session)

    total_members = (
        await session.execute(select(func.count()).select_from(User))
    ).scalar_one()
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
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=200),
) -> list[dict]:
    """Return all member profiles. Requires staff.members read permission."""
    await _require_rank("staff.members", "read", current_user, session)
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
    stmt = stmt.order_by(User.join_date.asc().nulls_last()).offset(skip).limit(limit)
    result = await session.execute(stmt)
    members: list[dict] = []
    for row in result:
        members.append(
            {
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
            }
        )
    return members


class StaffRsnUpdate(BaseModel):
    rsn: str | None


@router.patch("/members/{discord_user_id}/rsn")
async def update_member_rsn(
    discord_user_id: int,
    body: StaffRsnUpdate,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Set, change, or clear a member's RSN.

    Performs the same backfill and event-linking as the self-service
    PATCH /members/me/rsn endpoint. When the user already has an RSN the
    old name is cascaded across all player_name columns before the new one
    is applied.
    """
    await _require_rank("staff.members", "edit", current_user, session)

    new_rsn = body.rsn.strip() if body.rsn else None
    if new_rsn == "":
        new_rsn = None

    if new_rsn and not _RSN_RE.match(new_rsn):
        raise HTTPException(
            status_code=422,
            detail="RSN must be 1–12 characters: letters, numbers, spaces, hyphens, underscores.",
        )

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

    if new_rsn is None:
        await session.execute(
            update(User)
            .where(User.discord_user_id == discord_user_id)
            .values(rsn=None, updated_at=now)
        )
        if old_rsn:
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

    conflict = await session.execute(
        select(User.discord_user_id).where(
            func.lower(User.rsn) == new_rsn.lower(),
            User.discord_user_id != discord_user_id,
        )
    )
    if conflict.scalar_one_or_none():
        raise HTTPException(
            status_code=409, detail="RSN already linked to another account."
        )

    if old_rsn and old_rsn.lower() != new_rsn.lower():
        await cascade_rsn_change(session, old_rsn, new_rsn)
        logger.info(
            "staff/rsn: cascaded rename {!r} → {!r} for user {}",
            old_rsn,
            new_rsn,
            discord_user_id,
        )

    await session.execute(
        update(User)
        .where(User.discord_user_id == discord_user_id)
        .values(rsn=new_rsn, updated_at=now)
    )
    logger.info("staff/rsn: user {} set RSN {!r}", discord_user_id, new_rsn)

    backfill = await backfill_user_from_rsn(
        session,
        discord_user_id,
        new_rsn,
        clan_rank=user_row.clan_rank,
        total_loot_value=user_row.total_loot_value or 0,
        collection_log_slots=user_row.collection_log_slots or 0,
    )
    if backfill:
        logger.info(
            "staff/rsn: backfilled {} for user {}",
            list(backfill.keys()),
            discord_user_id,
        )

    event_result = await session.execute(
        update(Event)
        .where(func.lower(Event.player_name) == new_rsn.lower())
        .values(user_id=discord_user_id)
    )
    logger.info(
        "staff/rsn: linked user_id {} to {} event rows",
        discord_user_id,
        cast(CursorResult, event_result).rowcount,
    )

    await session.commit()
    return {"discord_user_id": discord_user_id, "rsn": new_rsn}


@router.get("/tickets")
async def staff_tickets(
    limit: int = Query(default=50, ge=1, le=200),
    skip: int = Query(default=0, ge=0),
    status: Literal["open", "closed"] | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Return tickets visible to the caller based on their rank."""
    roles = await _get_roles(current_user, session)
    if not await check_page_permission("staff.all-tickets", "read", roles, session):
        raise HTTPException(status_code=403, detail="Requires Mentor or higher.")

    # Bypass users see all ticket types; others are filtered by label-based rank check.
    bypass_roles = await get_admin_bypass_roles(session)
    if any(r in bypass_roles for r in roles):
        allowed = list(_TICKET_TYPE_MIN_RANK.keys())
    else:
        id_to_label = await get_role_label_map(session)
        role_labels = [id_to_label.get(r, r) for r in roles]
        allowed = _allowed_ticket_types(role_labels)

    if not allowed:
        return []

    stmt = (
        select(Ticket)
        .where(Ticket.ticket_type.in_(allowed))
        .order_by(Ticket.ticket_id.desc())
        .offset(skip)
        .limit(limit)
    )
    if status is not None:
        stmt = stmt.where(Ticket.status == status)

    result = await session.execute(stmt)
    ticket_rows = list(result.scalars())

    creator_ids = {row.creator_id for row in ticket_rows}
    user_result = await session.execute(
        select(User.discord_user_id, User.rsn, User.discord_avatar_url).where(
            User.discord_user_id.in_(creator_ids)
        )
    )
    user_map = {row.discord_user_id: row for row in user_result}

    missing_closed_ids = {
        row.ticket_id for row in ticket_rows
        if row.status == "closed" and row.closed_at is None
    }
    transcript_ts_map: dict[int, str] = {}
    if missing_closed_ids:
        ts_rows = await session.execute(
            text(
                "SELECT ticket_id, entries->-1->>'timestamp' AS last_ts"
                " FROM transcripts WHERE ticket_id = ANY(:ids)"
            ),
            {"ids": list(missing_closed_ids)},
        )
        transcript_ts_map = {
            r.ticket_id: r.last_ts for r in ts_rows if r.last_ts is not None
        }

    tickets: list[dict] = []
    for row in ticket_rows:
        u = user_map.get(row.creator_id)
        closed_at = (
            row.closed_at.isoformat()
            if row.closed_at
            else transcript_ts_map.get(row.ticket_id)
        )
        tickets.append(
            {
                "ticket_id": row.ticket_id,
                "guild_id": row.guild_id,
                "ticket_type": row.ticket_type,
                "status": row.status,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "closed_at": closed_at,
                "last_message_at": row.last_message_at.isoformat() if row.last_message_at else None,
                "creator": {
                    "id": row.creator_id,
                    "display_name": row.creator_name,
                    "avatar_url": u.discord_avatar_url if u else None,
                    "rsn": u.rsn if u else None,
                },
                "closed_by_id": row.closed_by_id,
                "close_reason": row.close_reason,
                "staff_note": row.staff_note,
            }
        )
    return tickets


@router.get("/tickets/{ticket_id}/transcript")
async def staff_ticket_transcript(
    ticket_id: int,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return the full transcript for a ticket the caller is authorised to view."""
    roles = await _get_roles(current_user, session)
    if not await check_page_permission("staff.all-tickets", "read", roles, session):
        raise HTTPException(status_code=403, detail="Requires Mentor or higher.")

    bypass_roles = await get_admin_bypass_roles(session)
    if any(r in bypass_roles for r in roles):
        allowed = list(_TICKET_TYPE_MIN_RANK.keys())
    else:
        id_to_label = await get_role_label_map(session)
        role_labels = [id_to_label.get(r, r) for r in roles]
        allowed = _allowed_ticket_types(role_labels)

    ticket_result = await session.execute(
        select(Ticket.ticket_type).where(
            Ticket.ticket_id == ticket_id,
            Ticket.ticket_type.in_(allowed),
        )
    )
    if not ticket_result.scalar_one_or_none():
        raise HTTPException(
            status_code=404, detail="Ticket not found or access denied."
        )

    tr_result = await session.execute(
        select(Transcript).where(Transcript.ticket_id == ticket_id)
    )
    tr = tr_result.scalar_one_or_none()
    if not tr:
        raise HTTPException(status_code=404, detail="Transcript not available.")

    raw = tr.entries
    entries = raw.get("entries", []) if isinstance(raw, dict) else (raw or [])
    return {"ticket_id": tr.ticket_id, "entries": entries}
