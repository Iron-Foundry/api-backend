from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    TileRaceEvent,
    TileRaceSignup,
    TileRaceTeam,
)
from app.dependencies import get_session
from app.services.page_permissions import require_page_permission

from ._helpers import _serialize_team
from .schemas import TeamBody, TeamPatch

router = APIRouter()
_PERM = Depends(require_page_permission("tilerace.admin", "edit"))


def _snake_draft(
    signups: list[TileRaceSignup], team_ids: list[int]
) -> dict[int, list[TileRaceSignup]]:
    n = len(team_ids)
    result: dict[int, list[TileRaceSignup]] = {tid: [] for tid in team_ids}
    if not n:
        return result
    sorted_sups = sorted(signups, key=lambda s: s.ranking_score, reverse=True)
    for i, sup in enumerate(sorted_sups):
        chunk = i // n
        pos = i % n
        idx = pos if chunk % 2 == 0 else n - 1 - pos
        result[team_ids[idx]].append(sup)
    return result


@router.post("/events/{event_id}/teams", status_code=201)
async def add_team(
    event_id: int,
    body: TeamBody,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
) -> dict[str, Any]:
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
        members=[],
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
    await session.delete(team)
    await session.commit()
    return {"ok": True}


@router.post("/events/{event_id}/teams/scramble")
async def scramble_teams(
    event_id: int,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
) -> dict[str, Any]:
    event = (
        await session.execute(select(TileRaceEvent).where(TileRaceEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")
    teams = (
        (
            await session.execute(
                select(TileRaceTeam)
                .where(TileRaceTeam.event_id == event_id)
                .order_by(TileRaceTeam.id)
            )
        )
        .scalars()
        .all()
    )
    signups = (
        (
            await session.execute(
                select(TileRaceSignup).where(TileRaceSignup.event_id == event_id)
            )
        )
        .scalars()
        .all()
    )
    if not teams or not signups:
        raise HTTPException(400, "Need both teams and signups to scramble.")
    team_ids = [t.id for t in teams]
    assignments = _snake_draft(list(signups), team_ids)
    now = datetime.now(UTC)
    for team in teams:
        assigned = assignments.get(team.id, [])
        captain_idx = next(
            (i for i, s in enumerate(assigned) if s.wants_captain),
            0 if assigned else None,
        )
        team.members = [
            {
                "discord_user_id": str(s.discord_user_id),
                "rsn": s.rsn,
                "ranking_score": s.ranking_score,
                "is_captain": i == captain_idx,
            }
            for i, s in enumerate(assigned)
        ]
        team.updated_at = now
    for signup in signups:
        await session.delete(signup)
    await session.commit()
    return {"ok": True, "teams": [_serialize_team(t) for t in teams]}
