"""Claim state: what a team's submissions mean for the board.

A tile is *claimed* the moment every requirement leaf carries a submission that
has not been rejected, which is what unlocks the next roll. Staff approval only
upgrades that row to *approved*; a rejection unpicks the claim and rolls the
team back to the tile it was proving.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    TileRaceCompletion,
    TileRaceEvent,
    TileRaceSubmission,
    TileRaceTeam,
    TileRepositoryTile,
)

from ._requirement_leaves import is_satisfied
from ._roll_effects import find_cell
from .requirement_schema import requirement_from_items

CLAIMED_STATUSES = ("claimed", "approved")


async def tile_at(
    session: AsyncSession, event: TileRaceEvent, path_position: int
) -> tuple[TileRepositoryTile | None, dict[str, Any] | None]:
    """The repository tile and requirement tree standing on one board position."""
    cell = find_cell(event.cells or [], path_position)
    tile_id = (cell or {}).get("tile_id")
    if not tile_id:
        return None, None
    tile = (
        await session.execute(
            select(TileRepositoryTile).where(TileRepositoryTile.id == int(tile_id))
        )
    ).scalar_one_or_none()
    if tile is None:
        return None, None
    return tile, tile.requirement or requirement_from_items(tile.items or [])


async def submissions_at(
    session: AsyncSession, team_id: int, path_position: int
) -> list[TileRaceSubmission]:
    return list(
        (
            await session.execute(
                select(TileRaceSubmission).where(
                    TileRaceSubmission.team_id == team_id,
                    TileRaceSubmission.path_position == path_position,
                )
            )
        )
        .scalars()
        .all()
    )


async def apply_claim_state(
    session: AsyncSession,
    event: TileRaceEvent,
    team: TileRaceTeam,
    path_position: int,
) -> str:
    """Recompute one board position for one team and return its claim status.

    Call after anything that creates, approves or rejects a submission. Flushes
    but never commits - the caller owns the transaction.
    """
    _tile, requirement = await tile_at(session, event, path_position)
    active = [
        s
        for s in await submissions_at(session, team.id, path_position)
        if s.status != "rejected"
    ]
    satisfied = is_satisfied(requirement, {s.leaf_key for s in active})
    now = datetime.now(UTC)
    row = await _completion_row(session, team.id, path_position)

    if not satisfied:
        _roll_back(team, path_position, now)
        if row is not None:
            row.status = "rejected"
            row.completed_at = now
        await session.flush()
        return "rejected" if row is not None else "none"

    status = "approved" if all(s.status == "approved" for s in active) else "claimed"
    if row is None:
        session.add(
            TileRaceCompletion(
                event_id=event.id,
                team_id=team.id,
                path_position=path_position,
                status=status,
                completed_by=active[0].discord_user_id if active else None,
                completed_at=now,
            )
        )
    else:
        row.status = status
        row.completed_at = now
    restore_position(team, path_position, now)
    await session.flush()
    return status


async def _completion_row(
    session: AsyncSession, team_id: int, path_position: int
) -> TileRaceCompletion | None:
    return (
        await session.execute(
            select(TileRaceCompletion).where(
                TileRaceCompletion.team_id == team_id,
                TileRaceCompletion.path_position == path_position,
            )
        )
    ).scalar_one_or_none()


def _roll_back(team: TileRaceTeam, path_position: int, now: datetime) -> None:
    """Send the team back to the tile it failed, remembering where it was.

    Only the marker moves. The furthest point is handed back by ``_restore`` the
    moment the tile is claimed again, so the grind in between is never lost.
    """
    if team.position <= path_position:
        return
    team.furthest_position = max(team.furthest_position, team.position)
    team.position = path_position
    team.updated_at = now


def restore_position(team: TileRaceTeam, path_position: int, now: datetime) -> None:
    """Hand a rolled-back team its active point back once it clears the tile."""
    if path_position != team.position or team.furthest_position <= team.position:
        return
    team.position = team.furthest_position
    team.furthest_position = 0
    team.updated_at = now
