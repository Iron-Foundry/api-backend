"""Roll feedback published to the rolling team's own Discord channel."""

from __future__ import annotations

from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

from app.db.models import TileRaceEvent, TileRaceTeam, TileRepositoryTile

from ._discord_payload import publish
from ._requirement_text import requirement_lines
from ._roll_effects import find_cell
from .requirement_schema import requirement_from_items


async def announce(
    session: AsyncSession,
    valkey: Valkey,
    event: TileRaceEvent,
    team: TileRaceTeam,
    roll: dict[str, Any],
    rolled_by: int,
    summary: dict[str, Any],
) -> bool:
    """Tell the team's channel what was rolled and what they landed on.

    Called after the roll is committed, so nothing here may raise: a team whose
    Discord is not provisioned simply gets no message, and a publish that fails
    must not turn a completed roll into an error.
    """
    if team.discord_text_channel_id is None:
        return False
    try:
        tile = await _tile(session, find_cell(event.cells or [], team.position))
        await publish(
            valkey,
            {
                "action": "roll",
                "event_id": str(event.id),
                "event_name": event.name,
                "channel_id": str(team.discord_text_channel_id),
                "rolled_by": str(rolled_by),
                "team": {
                    "team_id": str(team.id),
                    "name": team.name,
                    "color": team.color,
                },
                "roll": {**roll, "new_position": team.position},
                "tile": tile,
                "notes": _notes(summary),
            },
        )
    except Exception as exc:
        logger.warning("tilerace: roll feedback not published - {}", exc)
        return False
    return True


async def _tile(
    session: AsyncSession, cell: dict[str, Any] | None
) -> dict[str, Any] | None:
    tile_id = (cell or {}).get("tile_id")
    if not tile_id:
        return None
    row = (
        await session.execute(
            select(TileRepositoryTile).where(TileRepositoryTile.id == int(tile_id))
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    items = row.items or []
    return {
        "id": str(row.id),
        "title": row.title,
        "description": row.description,
        "icon_url": row.icon_url,
        "requirements": requirement_lines(
            row.requirement or requirement_from_items(items)
        ),
    }


def _notes(summary: dict[str, Any]) -> list[str]:
    """The landing's side effects, worded for the team reading the message."""
    notes: list[str] = []
    trap = summary.get("trap")
    if trap:
        notes.append(
            f"Trap on tile {trap['from']}! Rolled {trap['total']} "
            f"and slid back to tile {trap['to']}"
        )
    if summary.get("trap_spent") is not None:
        notes.append(f"Trap on tile {summary['trap_spent']} is already sprung")
    if summary.get("moved_to") is not None:
        notes.append(f"Moved to tile {summary['moved_to']}")
    if summary.get("allow_extra_roll"):
        notes.append("Bonus: roll again")
    if summary.get("skip_next"):
        notes.append("Trap: your next turn is skipped")
    if summary.get("reroll"):
        notes.append("Reroll granted")
    if summary.get("game_over"):
        notes.append("End pad reached - the race is over")
    return notes
