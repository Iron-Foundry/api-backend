from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TileRaceEvent, TileRaceTeam
from app.dependencies import get_current_user, get_session
from app.services.page_permissions import require_page_permission

from .schemas import FogBody, RollBody

router = APIRouter()
_FOG_PERM = Depends(require_page_permission("tilerace.admin", "edit"))


@router.post("/events/{event_id}/teams/{team_id}/roll")
async def roll_dice(
    event_id: int,
    team_id: int,
    body: RollBody,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    if body.roll < 1 or body.roll > 6:
        raise HTTPException(400, "Roll must be between 1 and 6.")
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
    user_id = str(current_user["sub"])
    members = team.members or []
    captain = next(
        (
            m
            for m in members
            if m.get("is_captain") and str(m.get("discord_user_id")) == user_id
        ),
        None,
    )
    if captain is None:
        raise HTTPException(403, "Only team captains may roll.")
    team.position = team.position + body.roll
    team.updated_at = datetime.now(timezone.utc)
    await session.commit()
    return {"roll": body.roll, "new_position": team.position}


@router.patch("/events/{event_id}/fog-of-war")
async def set_fog_of_war(
    event_id: int,
    body: FogBody,
    session: AsyncSession = Depends(get_session),
    _perm: None = _FOG_PERM,
) -> dict:
    event = (
        await session.execute(select(TileRaceEvent).where(TileRaceEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")
    event.fog_of_war = body.enabled
    event.updated_at = datetime.now(timezone.utc)
    await session.commit()
    return {"ok": True, "fog_of_war": body.enabled}
