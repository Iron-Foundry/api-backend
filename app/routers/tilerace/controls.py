from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

from app.db.models import (
    TileRaceCompletion,
    TileRaceEvent,
    TileRaceRoll,
    TileRaceSignup,
    TileRaceTeam,
)
from app.dependencies import get_current_user, get_session, get_valkey
from app.services.page_permissions import require_page_permission

from ._roll_effects import (
    apply_landing_modifiers,
    apply_pad_trigger,
    cell_in_pad,
    cell_is_gated,
    find_cell,
    roll_dice_values,
)
from ._roll_feed import announce
from ._setback import clear_tile_range
from ._submission_helpers import CLAIMED_STATUSES
from .schemas import FogBody

router = APIRouter()
_FOG_PERM = Depends(require_page_permission("tilerace.admin", "edit"))


async def _require_member(
    session: AsyncSession, team: TileRaceTeam, user_id: int
) -> None:
    member = (
        await session.execute(
            select(TileRaceSignup.id).where(
                TileRaceSignup.team_id == team.id,
                TileRaceSignup.discord_user_id == user_id,
            )
        )
    ).first()
    if member is None:
        raise HTTPException(403, "Only team members may roll.")


async def _claimed(session: AsyncSession, team_id: int, position: int) -> bool:
    """Whether the team has proof in for this tile.

    A claim is enough to roll on: teams do not wait for staff, and a rejection
    later rolls them back to this tile (see ``_submission_helpers``).
    """
    row = (
        await session.execute(
            select(TileRaceCompletion).where(
                TileRaceCompletion.team_id == team_id,
                TileRaceCompletion.path_position == position,
                TileRaceCompletion.status.in_(CLAIMED_STATUSES),
            )
        )
    ).scalar_one_or_none()
    return row is not None


@router.post("/events/{event_id}/teams/{team_id}/roll")
async def roll_dice(
    event_id: int,
    team_id: int,
    session: AsyncSession = Depends(get_session),
    valkey: Valkey = Depends(get_valkey),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Roll for a team and advance them along the board.

    Applies whatever modifier the landed tile carries.
    """
    try:
        team = (
            await session.execute(
                select(TileRaceTeam)
                .where(TileRaceTeam.id == team_id, TileRaceTeam.event_id == event_id)
                .with_for_update(nowait=True)
            )
        ).scalar_one_or_none()
    except OperationalError as exc:
        await session.rollback()
        raise HTTPException(
            409, "Someone else is already rolling for this team."
        ) from exc
    if team is None:
        raise HTTPException(404, "Team not found.")
    event = (
        await session.execute(select(TileRaceEvent).where(TileRaceEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")
    if event.is_finished:
        raise HTTPException(409, "Game over.")
    if event.rolls_paused:
        raise HTTPException(409, "Rolling is paused.")
    rolled_by = int(current_user["sub"])
    await _require_member(session, team, rolled_by)
    now = datetime.now(UTC)

    effects = dict(team.pending_effects or {})
    if effects.get("skip_next"):
        effects["skip_next"] = False
        team.pending_effects = effects
        team.updated_at = now
        session.add(
            TileRaceRoll(
                event_id=event_id,
                team_id=team_id,
                dice=[],
                roll=0,
                skipped=True,
                new_position=team.position,
                rolled_by=rolled_by,
                rolled_at=now,
            )
        )
        await session.commit()
        await announce(
            session,
            valkey,
            event,
            team,
            {"dice": [], "total": 0, "skipped": True},
            rolled_by,
            {},
        )
        return {"skipped": True, "new_position": team.position, "dice": []}

    cells = event.cells or []
    current = find_cell(cells, team.position)
    if cell_is_gated(current) and not await _claimed(session, team_id, team.position):
        raise HTTPException(409, "Submit proof for the current tile first.")

    dice = roll_dice_values(event.dice_count, event.dice_sides)
    roll = sum(dice)
    landed_on = team.position + roll
    team.position = landed_on
    summary = apply_landing_modifiers(team, find_cell(cells, landed_on))
    _apply_pads(event, team, find_cell(cells, team.position), summary)
    if team.position < landed_on:
        reset = await clear_tile_range(session, team_id, team.position, landed_on)
        if reset:
            summary["tiles_reset"] = reset
    team.updated_at = now
    session.add(
        TileRaceRoll(
            event_id=event_id,
            team_id=team_id,
            dice=dice,
            roll=roll,
            skipped=False,
            new_position=team.position,
            rolled_by=rolled_by,
            rolled_at=now,
        )
    )
    await session.commit()
    await announce(
        session,
        valkey,
        event,
        team,
        {"dice": dice, "total": roll, "skipped": False},
        rolled_by,
        summary,
    )
    return {"roll": roll, "dice": dice, "new_position": team.position, **summary}


def _apply_pads(
    event: TileRaceEvent,
    team: TileRaceTeam,
    cell: dict[str, Any] | None,
    summary: dict[str, Any],
) -> None:
    if cell_in_pad(cell, event.start_pad):
        apply_pad_trigger(team, event.start_pad, summary)
    if cell_in_pad(cell, event.end_pad):
        apply_pad_trigger(team, event.end_pad, summary)
        if (event.end_pad or {}).get("ends_game", True):
            event.is_finished = True
            event.winner_team_id = team.id
            event.updated_at = datetime.now(UTC)
            summary["game_over"] = True


@router.patch("/events/{event_id}/fog-of-war")
async def set_fog_of_war(
    event_id: int,
    body: FogBody,
    session: AsyncSession = Depends(get_session),
    _perm: None = _FOG_PERM,
) -> dict[str, Any]:
    """Toggle whether teams can see board positions they have not reached."""
    event = (
        await session.execute(select(TileRaceEvent).where(TileRaceEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")
    event.fog_of_war = body.enabled
    event.updated_at = datetime.now(UTC)
    await session.commit()
    return {"ok": True, "fog_of_war": body.enabled}
