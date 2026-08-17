"""The public recap of a finished event: graphs, standings, contributors."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    TileRaceCompletion,
    TileRaceEvent,
    TileRaceRoll,
    TileRaceSignup,
    TileRaceSubmission,
    TileRaceTeam,
)
from app.dependencies import get_session

from ._recap import recap_payload

router = APIRouter()


async def _rows(session: AsyncSession, model: Any, event_id: int) -> list[Any]:
    return list(
        (await session.execute(select(model).where(model.event_id == event_id)))
        .scalars()
        .all()
    )


async def _next_event(
    session: AsyncSession, event: TileRaceEvent
) -> dict[str, Any] | None:
    """The event that takes over from this one, running or still to start."""
    row = (
        await session.execute(
            select(TileRaceEvent)
            .where(
                TileRaceEvent.id != event.id,
                TileRaceEvent.is_finished.is_(False),
                or_(
                    TileRaceEvent.is_active.is_(True),
                    TileRaceEvent.starts_at > datetime.now(UTC),
                ),
            )
            .order_by(
                TileRaceEvent.is_active.desc(),
                TileRaceEvent.starts_at.asc().nulls_last(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return {
        "id": str(row.id),
        "name": row.name,
        "is_active": row.is_active,
        "starts_at": row.starts_at.isoformat() if row.starts_at else None,
    }


@router.get("/events/{event_id}/recap")
async def get_event_recap(
    event_id: int, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """Return a finished event's graphs, standings and contributors.

    Public, and aggregated to match: only counts and time series leave the API,
    never a proof URL, a review note or a Discord id. Racers removed from the
    roster during the event are dropped from every submission count, and how
    many were dropped rides along as `totals.removed_racers`.
    """
    event = (
        await session.execute(select(TileRaceEvent).where(TileRaceEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")
    return recap_payload(
        event,
        await _rows(session, TileRaceTeam, event_id),
        await _rows(session, TileRaceSignup, event_id),
        await _rows(session, TileRaceRoll, event_id),
        await _rows(session, TileRaceCompletion, event_id),
        await _rows(session, TileRaceSubmission, event_id),
        await _next_event(session, event),
    )
