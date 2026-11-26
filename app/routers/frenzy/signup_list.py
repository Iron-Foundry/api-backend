"""The staff list of a frenzy event's signups."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FrenzyEvent, FrenzySignup, User
from app.dependencies import get_session
from app.services.page_permissions import require_page_permission

from .signup_schemas import FrenzySignupList, FrenzySignupOut

router = APIRouter()

_PERM = Depends(require_page_permission("frenzy.admin", "edit"))


@router.get("/events/{event_id}/signups")
async def list_signups(
    event_id: int,
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
) -> FrenzySignupList:
    """The event's signups, oldest first, with the member's Discord name."""
    if await session.get(FrenzyEvent, event_id) is None:
        raise HTTPException(404, "Event not found.")
    of_event = FrenzySignup.event_id == event_id
    count = select(func.count()).select_from(FrenzySignup).where(of_event)
    total = await session.scalar(count) or 0
    rows = await session.execute(
        select(FrenzySignup, User.discord_username)
        .outerjoin(User, User.discord_user_id == FrenzySignup.discord_user_id)
        .where(of_event)
        .order_by(FrenzySignup.signed_up_at, FrenzySignup.id)
        .limit(limit)
        .offset(offset)
    )
    items = [
        FrenzySignupOut(
            id=s.id,
            wants_captain=s.wants_captain,
            discord_user_id=str(s.discord_user_id),
            discord_username=name,
            account_id=s.account_id,
            rsn=s.rsn,
            signed_up_at=s.signed_up_at,
        )
        for s, name in rows.all()
    ]
    return FrenzySignupList(items=items, total=total)
