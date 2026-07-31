from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    PlayerRanking,
    TileRaceEvent,
    TileRaceSignup,
    TileRaceTeam,
    UserAccount,
)


async def event_or_404(session: AsyncSession, event_id: int) -> TileRaceEvent:
    event = (
        await session.execute(select(TileRaceEvent).where(TileRaceEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")
    return event


async def find_entry(
    session: AsyncSession, event_id: int, discord_user_id: int
) -> TileRaceSignup | None:
    return (
        await session.execute(
            select(TileRaceSignup).where(
                TileRaceSignup.event_id == event_id,
                TileRaceSignup.discord_user_id == discord_user_id,
            )
        )
    ).scalar_one_or_none()


async def entry_or_404(
    session: AsyncSession, event_id: int, discord_user_id: int
) -> TileRaceSignup:
    entry = await find_entry(session, event_id, discord_user_id)
    if entry is None:
        raise HTTPException(404, "Not on this event's roster.")
    return entry


async def validate_team(
    session: AsyncSession, event_id: int, team_id: int | None
) -> None:
    if team_id is None:
        return
    row = (
        await session.execute(
            select(TileRaceTeam.id).where(
                TileRaceTeam.id == team_id, TileRaceTeam.event_id == event_id
            )
        )
    ).first()
    if row is None:
        raise HTTPException(404, "Team not found.")


async def primary_account(
    session: AsyncSession, discord_user_id: int
) -> UserAccount | None:
    return (
        (
            await session.execute(
                select(UserAccount)
                .where(UserAccount.discord_user_id == discord_user_id)
                .order_by(UserAccount.is_primary.desc(), UserAccount.created_at.asc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )


async def ranking_score(session: AsyncSession, rsn: str) -> int:
    ranking = (
        (
            await session.execute(
                select(PlayerRanking)
                .where(func.lower(PlayerRanking.rsn) == rsn.lower())
                .order_by(PlayerRanking.points.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    return ranking.points if ranking else 0


async def clear_captain(
    session: AsyncSession, team_id: int | None, keep_id: int | None = None
) -> None:
    """Demote every captain on a team, as its own statement.

    A partial unique index allows one captain per team, and Postgres checks it
    per statement, so the demotion must land before the promotion is flushed.
    """
    if team_id is None:
        return
    stmt = (
        update(TileRaceSignup)
        .where(TileRaceSignup.team_id == team_id, TileRaceSignup.is_captain.is_(True))
        .values(is_captain=False)
        .execution_options(synchronize_session="fetch")
    )
    if keep_id is not None:
        stmt = stmt.where(TileRaceSignup.id != keep_id)
    await session.execute(stmt)
    await session.flush()
