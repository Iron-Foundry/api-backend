from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TileRaceEvent, TileRaceTeam
from app.dependencies import get_session
from app.services.page_permissions import require_page_permission

from .schemas import TeamBody, TeamPatch

router = APIRouter()
_PERM = Depends(require_page_permission("tilerace.admin", "edit"))


async def _team_or_404(
    session: AsyncSession, event_id: int, team_id: int
) -> TileRaceTeam:
    team = (
        await session.execute(
            select(TileRaceTeam).where(
                TileRaceTeam.id == team_id,
                TileRaceTeam.event_id == event_id,
            )
        )
    ).scalar_one_or_none()
    if team is None:
        raise HTTPException(404, "Team not found.")
    return team


@router.post("/events/{event_id}/teams", status_code=201)
async def add_team(
    event_id: int,
    body: TeamBody,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
) -> dict[str, Any]:
    """Add a team to a tile race event."""
    event = (
        await session.execute(select(TileRaceEvent).where(TileRaceEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")
    team = TileRaceTeam(
        event_id=event_id,
        name=body.name,
        slug=body.slug,
        icon_type=body.icon_type,
        icon_url=body.icon_url,
        color=body.color,
        position=0,
        updated_at=datetime.now(UTC),
    )
    session.add(team)
    await session.commit()
    return {"id": str(team.id)}


@router.patch("/events/{event_id}/teams/{team_id}")
async def patch_team(
    event_id: int,
    team_id: int,
    body: TeamPatch,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
) -> dict[str, Any]:
    """Rename a team or restyle it. Rosters are edited through /roster."""
    team = await _team_or_404(session, event_id, team_id)
    if body.name is not None:
        team.name = body.name
    if body.slug is not None:
        team.slug = body.slug
    if body.icon_type is not None:
        team.icon_type = body.icon_type
    if body.icon_url is not None:
        team.icon_url = body.icon_url
    if body.color is not None:
        team.color = body.color
    if body.position is not None:
        team.position = body.position
    team.updated_at = datetime.now(UTC)
    await session.commit()
    return {"ok": True}


@router.delete("/events/{event_id}/teams/{team_id}")
async def delete_team(
    event_id: int,
    team_id: int,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
) -> dict[str, Any]:
    """Remove a team; its members fall back to the unassigned signup pool."""
    team = await _team_or_404(session, event_id, team_id)
    await session.delete(team)
    await session.commit()
    return {"ok": True}
