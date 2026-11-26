"""Staff routes that change a frenzy event's settings and which event runs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FrenzyEvent
from app.dependencies import get_session
from app.services.page_permissions import require_page_permission

from .schemas import EventPatch

router = APIRouter()

_PERM = Depends(require_page_permission("frenzy.admin", "edit"))


@router.patch("/events/{event_id}")
async def patch_event(
    event_id: int,
    body: EventPatch,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
) -> dict[str, Any]:
    """Update an event's schedule, settings, or linked WOM competition."""
    event = (
        await session.execute(select(FrenzyEvent).where(FrenzyEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")

    if body.name is not None:
        event.name = body.name
    if body.signups_open is not None:
        event.signups_open = body.signups_open
    if body.wom_comp_id is not None:
        event.wom_comp_id = body.wom_comp_id
    if body.leaderboard_metrics is not None:
        event.leaderboard_metrics = body.leaderboard_metrics
    if body.trusted_sources is not None:
        event.trusted_sources = body.trusted_sources
    if body.starts_at is not None:
        event.starts_at = body.starts_at
    if body.ends_at is not None:
        event.ends_at = body.ends_at
    event.updated_at = datetime.now(UTC)
    await session.commit()
    return {"ok": True}


@router.post("/events/{event_id}/activate")
async def activate_event(
    event_id: int, session: AsyncSession = Depends(get_session), _perm: None = _PERM
) -> dict[str, Any]:
    """Make this the running event, deactivating any other."""
    event = (
        await session.execute(select(FrenzyEvent).where(FrenzyEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")
    await session.execute(
        update(FrenzyEvent).where(FrenzyEvent.id != event_id).values(is_active=False)
    )
    event.is_active = True
    await session.commit()
    return {"ok": True, "active_event_id": event_id}


@router.post("/events/{event_id}/deactivate")
async def deactivate_event(
    event_id: int, session: AsyncSession = Depends(get_session), _perm: None = _PERM
) -> dict[str, Any]:
    """Stop the running event without deleting its progress."""
    event = (
        await session.execute(select(FrenzyEvent).where(FrenzyEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")
    event.is_active = False
    await session.commit()
    return {"ok": True}
