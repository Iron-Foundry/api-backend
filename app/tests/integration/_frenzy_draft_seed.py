"""Seed rows for the frenzy draft integration tests."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import (
    FrenzyDraft,
    FrenzyEvent,
    FrenzySignup,
    FrenzyTeam,
    FrenzyTemplate,
    PlayerRanking,
)

POOL = {"P1": 600, "P2": 500, "P3": 400, "P4": 300, "P5": 200, "P6": 100}


async def seed_event(engine: AsyncEngine) -> tuple[int, dict[str, int]]:
    """An event with two captains and six ranked signups; returns the signup ids by RSN."""
    now = datetime.now(UTC)
    async with AsyncSession(engine) as session:
        template = FrenzyTemplate(name="Seeded", created_at=now, updated_at=now)
        session.add(template)
        await session.flush()
        event = FrenzyEvent(
            name="Winter Frenzy",
            template_id=template.id,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add(event)
        await session.flush()
        signups = [
            FrenzySignup(
                event_id=event.id,
                discord_user_id=900_000 + i,
                rsn=rsn,
                timezone="Asia/Kolkata" if rsn == "P1" else None,
                signed_up_at=now,
            )
            for i, rsn in enumerate(["Cap A", "Cap B", *POOL])
        ]
        session.add_all(signups)
        session.add_all(
            PlayerRanking(rsn=rsn, rank="Ruby", points=pts, updated_at=now)
            for rsn, pts in POOL.items()
        )
        await session.flush()
        ids = (event.id, {s.rsn: s.id for s in signups})
        await session.commit()
    return ids


async def seed_picking(engine: AsyncEngine, event_id: int, ids: dict[str, int]) -> None:
    """A started draft, written directly, so no staff patch is active in the test."""
    now = datetime.now(UTC)
    async with AsyncSession(engine) as session:
        teams = [
            FrenzyTeam(event_id=event_id, name=n, slug=n, updated_at=now)
            for n in ("a", "b")
        ]
        session.add_all(teams)
        await session.flush()
        session.add(
            FrenzyDraft(
                event_id=event_id,
                mode="full",
                captain_ids=[ids["Cap A"], ids["Cap B"]],
                team_ids=[t.id for t in teams],
                state="picking",
                updated_at=now,
            )
        )
        await session.commit()


async def rosters(engine: AsyncEngine, event_id: int) -> dict[str, list[str]]:
    """Each team's participants, keyed by the team name."""
    async with AsyncSession(engine) as session:
        teams = await session.execute(
            select(FrenzyTeam).where(FrenzyTeam.event_id == event_id)
        )
        return {t.name: list(t.participants) for t in teams.scalars()}
