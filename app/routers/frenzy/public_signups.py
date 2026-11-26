"""The public list of the running frenzy event's signups."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FrenzyEvent
from app.dependencies import get_session

from ._draft_view import event_signups, member, rankings, strongest_first
from .draft_schemas import DraftMember

router = APIRouter()


class ActiveSignups(BaseModel):
    """The active event's signups, strongest ranking first, as the draft pool shows them."""

    event_id: int
    members: list[DraftMember]


@router.get("/active/signups")
async def get_active_signups(
    session: AsyncSession = Depends(get_session),
) -> ActiveSignups:
    """Return the active event's signups with each member's clan rank and points.

    The order matches the draft pool: highest ranking points first, and ties go to
    the earlier signup. Answers 404 with no active event.
    """
    event = (
        await session.execute(
            select(FrenzyEvent).where(FrenzyEvent.is_active.is_(True))
        )
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "No active frenzy event.")
    signups = await event_signups(session, event.id)
    ranked = await rankings(session, [s.rsn for s in signups])
    return ActiveSignups(
        event_id=event.id,
        members=[member(s, ranked) for s in strongest_first(signups, ranked)],
    )
