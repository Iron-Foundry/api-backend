"""Staff router — rank-protected endpoints for staff-only operations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Ticket, Transcript, User
from app.dependencies import get_current_user, get_session

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
) -> list[dict]:
    """Return all member profiles. Requires Moderator or higher."""
    await _require_rank("Moderator", current_user, session)
    result = await session.execute(
        select(
            User.discord_user_id,
            User.discord_username,
            User.rsn,
            User.clan_rank,
            User.discord_roles,
            User.stats_opt_out,
            User.join_date,
            User.created_at,
            User.total_loot_value,
            User.collection_log_slots,
        ).order_by(User.join_date.asc().nulls_last())
    )
    members: list[dict] = []
    for row in result:
        members.append({
            "discord_user_id": row.discord_user_id,
            "discord_username": row.discord_username,
            "rsn": row.rsn,
            "clan_rank": row.clan_rank,
            "discord_roles": row.discord_roles,
            "stats_opt_out": row.stats_opt_out,
            "join_date": row.join_date.isoformat() if row.join_date else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "total_loot_value": row.total_loot_value,
            "collection_log_slots": row.collection_log_slots,
        })
    return members


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

    return {"ticket_id": tr.ticket_id, "entries": tr.entries}
