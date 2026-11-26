"""Staff routes that list, create, read and delete frenzy events."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FrenzyEvent, FrenzyTeam, FrenzyTemplate
from app.dependencies import get_current_user, get_session
from app.services.page_permissions import require_page_permission

from .schemas import EventBody

router = APIRouter()

_PERM = Depends(require_page_permission("frenzy.admin", "edit"))


@router.get("/events")
async def list_events(
    session: AsyncSession = Depends(get_session), _perm: None = _PERM
) -> list[dict[str, Any]]:
    """List every frenzy event with its template and team summary."""
    rows = (
        (
            await session.execute(
                select(FrenzyEvent).order_by(FrenzyEvent.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": e.id,
            "name": e.name,
            "template_id": e.template_id,
            "wom_comp_id": e.wom_comp_id,
            "starts_at": e.starts_at.isoformat() if e.starts_at else None,
            "ends_at": e.ends_at.isoformat() if e.ends_at else None,
            "is_active": e.is_active,
            "signups_open": e.signups_open,
            "created_at": e.created_at.isoformat(),
        }
        for e in rows
    ]


@router.post("/events", status_code=201)
async def create_event(
    body: EventBody,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a frenzy event from a template."""
    tmpl = (
        await session.execute(
            select(FrenzyTemplate).where(FrenzyTemplate.id == body.template_id)
        )
    ).scalar_one_or_none()
    if tmpl is None:
        raise HTTPException(404, "Template not found.")

    now = datetime.now(UTC)
    event = FrenzyEvent(
        name=body.name,
        template_id=body.template_id,
        wom_comp_id=body.wom_comp_id,
        leaderboard_metrics=body.leaderboard_metrics,
        trusted_sources=body.trusted_sources,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        is_active=False,
        created_by=int(current_user["sub"]),
        created_at=now,
        updated_at=now,
    )
    session.add(event)
    await session.commit()
    return {"id": event.id}


@router.get("/events/{event_id}")
async def get_event(
    event_id: int, session: AsyncSession = Depends(get_session), _perm: None = _PERM
) -> dict[str, Any]:
    """Return one event with its teams, tasks, and current scores."""
    event = (
        await session.execute(select(FrenzyEvent).where(FrenzyEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")

    teams = (
        (
            await session.execute(
                select(FrenzyTeam)
                .where(FrenzyTeam.event_id == event_id)
                .order_by(FrenzyTeam.sort_order)
            )
        )
        .scalars()
        .all()
    )

    return {
        "id": event.id,
        "name": event.name,
        "template_id": event.template_id,
        "wom_comp_id": event.wom_comp_id,
        "leaderboard_metrics": event.leaderboard_metrics,
        "trusted_sources": event.trusted_sources or [],
        "starts_at": event.starts_at.isoformat() if event.starts_at else None,
        "ends_at": event.ends_at.isoformat() if event.ends_at else None,
        "is_active": event.is_active,
        "signups_open": event.signups_open,
        "created_at": event.created_at.isoformat(),
        "teams": [
            {
                "id": t.id,
                "name": t.name,
                "slug": t.slug,
                "icon_url": t.icon_url,
                "sort_order": t.sort_order,
                "participants": t.participants or [],
            }
            for t in teams
        ],
    }


@router.delete("/events/{event_id}")
async def delete_event(
    event_id: int, session: AsyncSession = Depends(get_session), _perm: None = _PERM
) -> dict[str, Any]:
    """Delete an event along with its teams and submissions."""
    event = (
        await session.execute(select(FrenzyEvent).where(FrenzyEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")
    await session.delete(event)
    await session.commit()
    return {"ok": True}
