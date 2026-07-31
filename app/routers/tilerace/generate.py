from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    TileRaceCompletion,
    TileRaceEvent,
    TileRaceRoll,
    TileRaceSignup,
    TileRaceTeam,
)
from app.dependencies import get_session
from app.services.page_permissions import require_page_permission

from ._draft import (
    balance_raiders,
    pick_captain,
    snake_draft,
    target_sizes,
)
from ._helpers import _serialize_team, raids_kc_map
from ._teams_shape import reconcile_teams
from .schemas import GenerateTeamsBody

router = APIRouter()
_PERM = Depends(require_page_permission("tilerace.admin", "edit"))


async def _load(
    session: AsyncSession, event_id: int
) -> tuple[TileRaceEvent, list[TileRaceTeam], list[TileRaceSignup]]:
    event = (
        await session.execute(select(TileRaceEvent).where(TileRaceEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")
    teams = list(
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
    signups = list(
        (
            await session.execute(
                select(TileRaceSignup).where(TileRaceSignup.event_id == event_id)
            )
        )
        .scalars()
        .all()
    )
    return event, teams, signups


async def _has_progress(session: AsyncSession, event_id: int) -> bool:
    for model in (TileRaceRoll, TileRaceCompletion):
        row = (
            await session.execute(
                select(model.id).where(model.event_id == event_id).limit(1)
            )
        ).first()
        if row is not None:
            return True
    return False


async def _clear_assignments(session: AsyncSession, event_id: int) -> None:
    """Wipe every assignment as its own statement, before the new one is flushed.

    One captain per team is enforced by a partial unique index, which Postgres
    checks per statement; clearing first keeps a captain swap from tripping it.
    """
    await session.execute(
        update(TileRaceSignup)
        .where(TileRaceSignup.event_id == event_id)
        .values(team_id=None, is_captain=False)
        .execution_options(synchronize_session="fetch")
    )
    await session.flush()


def _raider_ids(
    signups: list[TileRaceSignup], kc_map: dict[str, int], threshold: int
) -> set[int]:
    return {s.id for s in signups if kc_map.get(s.rsn.lower(), 0) >= threshold}


@router.post("/events/{event_id}/teams/generate")
async def generate_teams(
    event_id: int,
    body: GenerateTeamsBody,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
) -> dict[str, Any]:
    """Build teams from the signup pool at the given team size and draft them.

    Teams are sized so none exceeds `team_size`; existing teams keep their name,
    colour and icon, surplus teams are removed. Signups are never deleted, so
    `POST .../teams/reset` returns the event to bare signups.
    """
    event, teams, signups = await _load(session, event_id)
    if not signups:
        raise HTTPException(400, "No signups to draft.")
    capacities = target_sizes(len(signups), body.team_size)
    if len(capacities) < len(teams) and await _has_progress(session, event_id):
        raise HTTPException(
            409,
            "This size would delete teams that already have rolls or completions.",
        )
    teams = await reconcile_teams(session, event_id, teams, len(capacities))
    team_ids = [t.id for t in teams]
    assignments = snake_draft(signups, team_ids, capacities)
    kc_map = await raids_kc_map(session, signups)
    if body.balance_raids_kc:
        balance_raiders(
            assignments, _raider_ids(signups, kc_map, body.raids_kc_threshold)
        )
    now = datetime.now(UTC)
    await _clear_assignments(session, event_id)
    for team_id, members in assignments.items():
        captain_id = pick_captain(members)
        for signup in members:
            signup.team_id = team_id
            signup.is_captain = signup.id == captain_id
    for team in teams:
        team.updated_at = now
    event.team_size = body.team_size
    event.updated_at = now
    await session.commit()
    rosters = {tid: list(members) for tid, members in assignments.items()}
    return {
        "ok": True,
        "teams": [_serialize_team(t, rosters.get(t.id, []), kc_map) for t in teams],
    }


@router.post("/events/{event_id}/teams/reset")
async def reset_teams(
    event_id: int,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
) -> dict[str, Any]:
    """Return the event to bare signups: every member is unassigned, teams stay."""
    event = (
        await session.execute(select(TileRaceEvent).where(TileRaceEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")
    await session.execute(
        update(TileRaceSignup)
        .where(TileRaceSignup.event_id == event_id)
        .values(team_id=None, is_captain=False)
    )
    event.updated_at = datetime.now(UTC)
    await session.commit()
    return {"ok": True}
