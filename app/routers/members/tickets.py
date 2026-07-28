from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Ticket, Transcript
from app.dependencies import get_current_user, get_session

router = APIRouter()


@router.get("/me/tickets")
async def member_tickets(
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """List the support tickets the signed-in member has opened."""
    discord_user_id = int(current_user["sub"])
    result = await session.execute(
        select(Ticket)
        .where(Ticket.creator_id == discord_user_id)
        .order_by(Ticket.ticket_id.desc())
    )
    return [
        {
            "ticket_id": row.ticket_id,
            "ticket_type": row.ticket_type,
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "closed_at": row.closed_at.isoformat() if row.closed_at else None,
            "last_message_at": row.last_message_at.isoformat()
            if row.last_message_at
            else None,
            "close_reason": row.close_reason,
        }
        for row in result.scalars()
    ]


@router.get("/me/tickets/{ticket_id}/transcript")
async def member_ticket_transcript(
    ticket_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return transcript for one of the authenticated user's tickets. staff_note is never returned."""
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
    raw = tr.entries
    entries = raw.get("entries", []) if isinstance(raw, dict) else (raw or [])
    return {"ticket_id": tr.ticket_id, "entries": entries}
