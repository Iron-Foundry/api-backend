"""What a backwards landing costs: the ground it gave up is the team's to earn again.

A trap or a backwards jump moves the marker but nothing else. Left alone, every
completion row across the stretch the team was thrown back over still reads as
claimed, so the gate in ``controls`` waves each of those rolls straight through
and the Submit button finds every requirement leaf already covered - the setback
costs the team nothing and they cannot re-prove those tiles even if they want to.

Clearing only the tile they came to rest on is not enough: the next roll carries
them onto the ones in between, and each of those is a free roll for the same
reason. The whole span from where they landed up to the tile that threw them
back is reset together.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TileRaceCompletion, TileRaceSubmission


async def clear_tile_range(
    session: AsyncSession, team_id: int, first: int, last: int
) -> list[int]:
    """Drop a team's completions and proof across a span of board positions.

    Both ends are inclusive. Returns the positions that actually held state, in
    board order. Flushes but never commits - the caller owns the transaction.
    """
    positions = sorted(await _positions_with_state(session, team_id, first, last))
    if not positions:
        return []
    await session.execute(
        delete(TileRaceSubmission).where(
            TileRaceSubmission.team_id == team_id,
            TileRaceSubmission.path_position.in_(positions),
        )
    )
    await session.execute(
        delete(TileRaceCompletion).where(
            TileRaceCompletion.team_id == team_id,
            TileRaceCompletion.path_position.in_(positions),
        )
    )
    await session.flush()
    return positions


async def _positions_with_state(
    session: AsyncSession, team_id: int, first: int, last: int
) -> set[int]:
    completions = (
        (
            await session.execute(
                select(TileRaceCompletion.path_position)
                .where(
                    TileRaceCompletion.team_id == team_id,
                    TileRaceCompletion.path_position.between(first, last),
                )
                .distinct()
            )
        )
        .scalars()
        .all()
    )
    submissions = (
        (
            await session.execute(
                select(TileRaceSubmission.path_position)
                .where(
                    TileRaceSubmission.team_id == team_id,
                    TileRaceSubmission.path_position.between(first, last),
                )
                .distinct()
            )
        )
        .scalars()
        .all()
    )
    return {*completions, *submissions}
