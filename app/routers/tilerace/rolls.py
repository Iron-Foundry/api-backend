from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TileRaceEvent, TileRaceRoll
from app.dependencies import get_current_user, get_session

from ._helpers import _serialize_roll

router = APIRouter()

_MAX_LIMIT = 100


@router.get("/events/{event_id}/rolls")
async def list_rolls(
    event_id: int,
    limit: int = 25,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> list[dict]:
    event = (
        await session.execute(select(TileRaceEvent).where(TileRaceEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")
    clamped_limit = max(1, min(limit, _MAX_LIMIT))
    rows = (
        (
            await session.execute(
                select(TileRaceRoll)
                .where(TileRaceRoll.event_id == event_id)
                .order_by(TileRaceRoll.rolled_at.desc())
                .limit(clamped_limit)
            )
        )
        .scalars()
        .all()
    )
    return [_serialize_roll(r) for r in rows]
