from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TileRaceEvent, TileRaceSignup, TileRaceTeam
from app.dependencies import get_current_user, get_session
from app.services.page_permissions import require_page_permission

from ._helpers import (
    _embed_cells,
    _serialize_signup,
    _serialize_summary,
    _serialize_team,
)
from .schemas import EventBody, EventPatch

router = APIRouter()
_PERM = Depends(require_page_permission("tilerace.admin", "edit"))


async def _full_event(event: TileRaceEvent, session: AsyncSession) -> dict:
    teams = (
        (
            await session.execute(
                select(TileRaceTeam)
                .where(TileRaceTeam.event_id == event.id)
                .order_by(TileRaceTeam.id)
            )
        )
        .scalars()
        .all()
    )
    signups = (
        (
            await session.execute(
                select(TileRaceSignup)
                .where(TileRaceSignup.event_id == event.id)
                .order_by(TileRaceSignup.signed_up_at)
            )
        )
        .scalars()
        .all()
    )
    cells = await _embed_cells(event.cells or [], session)
    return {
        **_serialize_summary(event),
        "cells": cells,
        "teams": [_serialize_team(t) for t in teams],
        "signups": [_serialize_signup(s) for s in signups],
    }


@router.get("/active")
async def get_active_event(session: AsyncSession = Depends(get_session)) -> dict:
    event = (
        await session.execute(
            select(TileRaceEvent).where(TileRaceEvent.is_active.is_(True))
        )
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "No active tile race event.")
    return await _full_event(event, session)


@router.get("/events")
async def list_events(
    session: AsyncSession = Depends(get_session), _perm: None = _PERM
) -> list[dict]:
    rows = (
        (
            await session.execute(
                select(TileRaceEvent).order_by(TileRaceEvent.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_serialize_summary(e) for e in rows]


@router.post("/events", status_code=201)
async def create_event(
    body: EventBody,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
    current_user: dict = Depends(get_current_user),
) -> dict:
    now = datetime.now(timezone.utc)
    event = TileRaceEvent(
        name=body.name,
        is_active=False,
        fog_of_war=False,
        grid_cols=body.grid_cols,
        grid_rows=body.grid_rows,
        background_url=body.background_url,
        cells=[],
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        created_by=int(current_user["sub"]),
        created_at=now,
        updated_at=now,
    )
    session.add(event)
    await session.commit()
    return {"id": str(event.id)}


@router.get("/events/{event_id}")
async def get_event(
    event_id: int,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
) -> dict:
    event = (
        await session.execute(select(TileRaceEvent).where(TileRaceEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")
    return await _full_event(event, session)


@router.patch("/events/{event_id}")
async def patch_event(
    event_id: int,
    body: EventPatch,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
) -> dict:
    event = (
        await session.execute(select(TileRaceEvent).where(TileRaceEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")
    if body.name is not None:
        event.name = body.name
    if body.grid_cols is not None:
        event.grid_cols = body.grid_cols
    if body.grid_rows is not None:
        event.grid_rows = body.grid_rows
    if body.background_url is not None:
        event.background_url = body.background_url
    if body.fog_of_war is not None:
        event.fog_of_war = body.fog_of_war
    if body.cells is not None:
        event.cells = list(body.cells)
    if body.starts_at is not None:
        event.starts_at = body.starts_at
    if body.ends_at is not None:
        event.ends_at = body.ends_at
    event.updated_at = datetime.now(timezone.utc)
    await session.commit()
    return {"ok": True}


@router.delete("/events/{event_id}")
async def delete_event(
    event_id: int,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
) -> dict:
    event = (
        await session.execute(select(TileRaceEvent).where(TileRaceEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")
    await session.delete(event)
    await session.commit()
    return {"ok": True}


@router.post("/events/{event_id}/activate")
async def activate_event(
    event_id: int,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
) -> dict:
    event = (
        await session.execute(select(TileRaceEvent).where(TileRaceEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")
    await session.execute(
        update(TileRaceEvent)
        .where(TileRaceEvent.id != event_id)
        .values(is_active=False)
    )
    event.is_active = True
    await session.commit()
    return {"ok": True, "active_event_id": event_id}


@router.post("/events/{event_id}/deactivate")
async def deactivate_event(
    event_id: int,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
) -> dict:
    event = (
        await session.execute(select(TileRaceEvent).where(TileRaceEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")
    event.is_active = False
    await session.commit()
    return {"ok": True}
