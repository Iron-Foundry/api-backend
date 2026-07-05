from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

from app.db.models import FrenzyEvent, FrenzyTeam
from app.dependencies import get_session, get_valkey
from app.services.page_permissions import require_page_permission

from ._constants import _LB_FRESH_KEY
from ._osrs_cache import _build_lb_cache
from .schemas import TeamBody, TeamPatch

router = APIRouter()

_PERM = Depends(require_page_permission("frenzy", "edit"))


@router.post("/events/{event_id}/teams", status_code=201)
async def add_team(
    event_id: int,
    body: TeamBody,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
) -> dict:
    event = (
        await session.execute(select(FrenzyEvent).where(FrenzyEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")

    existing = (
        await session.execute(
            select(FrenzyTeam).where(
                FrenzyTeam.event_id == event_id, FrenzyTeam.slug == body.slug
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            409, f"Team with slug '{body.slug}' already exists in this event."
        )

    now = datetime.now(timezone.utc)
    team = FrenzyTeam(
        event_id=event_id,
        name=body.name,
        slug=body.slug,
        icon_url=body.icon_url,
        sort_order=body.sort_order,
        participants=[],
        item_progress={},
        activity_progress={},
        milestone_progress={},
        updated_at=now,
    )
    session.add(team)
    await session.commit()
    return {"id": team.id, "slug": team.slug}


@router.patch("/events/{event_id}/teams/{team_slug}")
async def patch_team(
    event_id: int,
    team_slug: str,
    body: TeamPatch,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
) -> dict:
    team = (
        await session.execute(
            select(FrenzyTeam).where(
                FrenzyTeam.event_id == event_id, FrenzyTeam.slug == team_slug
            )
        )
    ).scalar_one_or_none()
    if team is None:
        raise HTTPException(404, "Team not found.")

    if body.name is not None:
        team.name = body.name
    if body.icon_url is not None:
        team.icon_url = body.icon_url
    if body.sort_order is not None:
        team.sort_order = body.sort_order
    if body.item_progress is not None:
        team.item_progress = body.item_progress
    if body.activity_progress is not None:
        team.activity_progress = body.activity_progress
    if body.milestone_progress is not None:
        team.milestone_progress = body.milestone_progress
    team.updated_at = datetime.now(timezone.utc)
    await session.commit()
    return {"ok": True}


@router.delete("/events/{event_id}/teams/{team_slug}")
async def delete_team(
    event_id: int,
    team_slug: str,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
) -> dict:
    team = (
        await session.execute(
            select(FrenzyTeam).where(
                FrenzyTeam.event_id == event_id, FrenzyTeam.slug == team_slug
            )
        )
    ).scalar_one_or_none()
    if team is None:
        raise HTTPException(404, "Team not found.")
    await session.delete(team)
    await session.commit()
    return {"ok": True}


@router.post("/leaderboards/refresh")
async def refresh_leaderboards(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    valkey: Valkey = Depends(get_valkey),
    _perm: None = _PERM,
) -> dict:
    await valkey.delete(_LB_FRESH_KEY)
    event = (
        await session.execute(
            select(FrenzyEvent).where(FrenzyEvent.is_active.is_(True))
        )
    ).scalar_one_or_none()
    metrics: list[str] = event.leaderboard_metrics if event else []
    wom_comp_id: int | None = event.wom_comp_id if event else None
    background_tasks.add_task(_build_lb_cache, valkey, wom_comp_id, metrics)
    return {"ok": True}
