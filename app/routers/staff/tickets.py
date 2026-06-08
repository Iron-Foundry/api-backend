from __future__ import annotations

from datetime import date, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Literal

from app.db.models import Ticket, Transcript, User
from app.dependencies import get_current_user, get_session
from app.services.page_permissions import check_page_permission

from ._helpers import get_allowed_ticket_types, get_roles

router = APIRouter()

_BOGUS_DATE = date(2026, 4, 14)


@router.get("/tickets")
async def staff_tickets(
    limit: int = Query(default=50, ge=1, le=200),
    skip: int = Query(default=0, ge=0),
    status: Literal["open", "closed"] | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Return tickets visible to the caller based on their rank."""
    roles = await get_roles(current_user, session)
    if not await check_page_permission("staff.all-tickets", "read", roles, session):
        raise HTTPException(403, "Requires Mentor or higher.")

    allowed = await get_allowed_ticket_types(roles, session)
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

    ticket_rows = list((await session.execute(stmt)).scalars())

    creator_ids = {row.creator_id for row in ticket_rows}
    user_map = {
        row.discord_user_id: row
        for row in (
            await session.execute(
                select(User.discord_user_id, User.rsn, User.discord_avatar_url).where(
                    User.discord_user_id.in_(creator_ids)
                )
            )
        )
    }

    needs_transcript = {
        row.ticket_id
        for row in ticket_rows
        if (row.status == "closed" and row.closed_at is None)
        or (row.created_at and row.created_at.astimezone(timezone.utc).date() == _BOGUS_DATE)
    }
    transcript_ts_map: dict[int, dict[str, str | None]] = {}
    if needs_transcript:
        ts_rows = await session.execute(
            text(
                "SELECT ticket_id,"
                " entries->0->>'timestamp' AS first_ts,"
                " entries->-1->>'timestamp' AS last_ts"
                " FROM transcripts WHERE ticket_id = ANY(:ids)"
            ),
            {"ids": list(needs_transcript)},
        )
        transcript_ts_map = {r.ticket_id: {"first_ts": r.first_ts, "last_ts": r.last_ts} for r in ts_rows}

    tickets: list[dict] = []
    for row in ticket_rows:
        u = user_map.get(row.creator_id)
        td = transcript_ts_map.get(row.ticket_id, {})
        bogus_created = (
            row.created_at is not None
            and row.created_at.astimezone(timezone.utc).date() == _BOGUS_DATE
        )
        created_at = (
            td.get("first_ts") or row.created_at.isoformat() if bogus_created
            else (row.created_at.isoformat() if row.created_at else None)
        )
        tickets.append({
            "ticket_id": row.ticket_id,
            "guild_id": row.guild_id,
            "ticket_type": row.ticket_type,
            "status": row.status,
            "created_at": created_at,
            "closed_at": row.closed_at.isoformat() if row.closed_at else td.get("last_ts"),
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
        })
    return tickets


@router.get("/tickets/{ticket_id}/transcript")
async def staff_ticket_transcript(
    ticket_id: int,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return the full transcript for a ticket the caller is authorised to view."""
    roles = await get_roles(current_user, session)
    if not await check_page_permission("staff.all-tickets", "read", roles, session):
        raise HTTPException(403, "Requires Mentor or higher.")

    allowed = await get_allowed_ticket_types(roles, session)
    ticket_result = await session.execute(
        select(Ticket.ticket_type).where(Ticket.ticket_id == ticket_id, Ticket.ticket_type.in_(allowed))
    )
    if not ticket_result.scalar_one_or_none():
        raise HTTPException(404, "Ticket not found or access denied.")

    tr = (
        await session.execute(select(Transcript).where(Transcript.ticket_id == ticket_id))
    ).scalar_one_or_none()
    if not tr:
        raise HTTPException(404, "Transcript not available.")

    raw = tr.entries
    entries = raw.get("entries", []) if isinstance(raw, dict) else (raw or [])
    return {"ticket_id": tr.ticket_id, "entries": entries}
