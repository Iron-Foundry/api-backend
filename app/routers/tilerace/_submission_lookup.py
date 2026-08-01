"""Reading a team's submission position: who they are, what they still owe."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    TileRaceEvent,
    TileRaceSignup,
    TileRaceSubmission,
    TileRaceTeam,
    TileRepositoryTile,
)

from ._requirement_state import leaf_catalog, outstanding_count
from ._requirement_text import requirement_lines
from ._submission_helpers import tile_at

VALID_STATUSES = ("pending", "approved", "rejected")


async def team_for_member(
    session: AsyncSession, event_id: int, discord_user_id: int
) -> tuple[TileRaceTeam, TileRaceSignup]:
    signup = (
        await session.execute(
            select(TileRaceSignup).where(
                TileRaceSignup.event_id == event_id,
                TileRaceSignup.discord_user_id == discord_user_id,
            )
        )
    ).scalar_one_or_none()
    if signup is None or signup.team_id is None:
        raise HTTPException(403, "You are not on a team in this event.")
    team = (
        await session.execute(
            select(TileRaceTeam).where(TileRaceTeam.id == signup.team_id)
        )
    ).scalar_one_or_none()
    if team is None:
        raise HTTPException(404, "Team not found.")
    return team, signup


async def submission_context(
    session: AsyncSession, discord_user_id: int
) -> dict[str, Any]:
    """Everything the Submit button needs: event, team, current tile, leaves."""
    event = (
        await session.execute(
            select(TileRaceEvent)
            .where(TileRaceEvent.is_active.is_(True))
            .order_by(TileRaceEvent.id.desc())
        )
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "No active tile race.")
    team, _signup = await team_for_member(session, event.id, discord_user_id)
    tile, requirement = await tile_at(session, event, team.position)
    covered = {
        s.leaf_key for s in await active_submissions(session, team.id, team.position)
    }
    return {
        "event_id": str(event.id),
        "event_name": event.name,
        "is_finished": event.is_finished,
        "team": {
            "id": str(team.id),
            "name": team.name,
            "slug": team.slug,
            "color": team.color,
        },
        "path_position": team.position,
        "tile": _tile_summary(tile),
        "leaves": leaf_catalog(requirement, covered),
        "outstanding": outstanding_count(requirement, covered),
        "requirement_lines": requirement_lines(requirement, covered),
    }


async def active_submissions(
    session: AsyncSession, team_id: int, path_position: int
) -> list[TileRaceSubmission]:
    """Every submission for one board position that has not been rejected."""
    return list(
        (
            await session.execute(
                select(TileRaceSubmission).where(
                    TileRaceSubmission.team_id == team_id,
                    TileRaceSubmission.path_position == path_position,
                    TileRaceSubmission.status != "rejected",
                )
            )
        )
        .scalars()
        .all()
    )


def _tile_summary(tile: TileRepositoryTile | None) -> dict[str, Any] | None:
    if tile is None:
        return None
    return {
        "id": str(tile.id),
        "title": tile.title,
        "description": tile.description,
        "icon_url": tile.icon_url,
    }
