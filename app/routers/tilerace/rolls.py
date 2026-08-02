from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TileRaceEvent, TileRaceRoll
from app.dependencies import get_current_user, get_session

from ._serializers import _serialize_roll

router = APIRouter()


@router.get("/events/{event_id}/rolls")
async def list_rolls(
    event_id: int,
    limit: int | None = Query(default=None, ge=1),
    session: AsyncSession = Depends(get_session),
    _current_user: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List an event's dice rolls, newest first. Omit `limit` for full history."""
    event = (
        await session.execute(select(TileRaceEvent).where(TileRaceEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")
    stmt = (
        select(TileRaceRoll)
        .where(TileRaceRoll.event_id == event_id)
        .order_by(TileRaceRoll.rolled_at.desc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return [_serialize_roll(r) for r in rows]
