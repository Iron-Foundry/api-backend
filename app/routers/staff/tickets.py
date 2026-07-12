from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Literal

from app.db.models import Ticket, Transcript
from app.dependencies import get_current_user, get_session
from app.services.page_permissions import check_page_permission

from ._helpers import get_allowed_ticket_types, get_roles
from ._ticket_serialize import serialize_tickets

router = APIRouter()


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
    return await serialize_tickets(ticket_rows, session)


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
        select(Ticket.ticket_type).where(
            Ticket.ticket_id == ticket_id, Ticket.ticket_type.in_(allowed)
        )
    )
    if not ticket_result.scalar_one_or_none():
        raise HTTPException(404, "Ticket not found or access denied.")

    tr = (
        await session.execute(
            select(Transcript).where(Transcript.ticket_id == ticket_id)
        )
    ).scalar_one_or_none()
    if not tr:
        raise HTTPException(404, "Transcript not available.")

    raw = tr.entries
    entries = raw.get("entries", []) if isinstance(raw, dict) else (raw or [])
    return {"ticket_id": tr.ticket_id, "entries": entries}
