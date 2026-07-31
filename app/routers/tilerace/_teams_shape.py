from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TileRaceTeam

TEAM_COLORS = (
    "#ef4444",
    "#3b82f6",
    "#22c55e",
    "#eab308",
    "#a855f7",
    "#f97316",
    "#14b8a6",
    "#ec4899",
    "#64748b",
    "#84cc16",
)


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "team"


async def reconcile_teams(
    session: AsyncSession,
    event_id: int,
    teams: list[TileRaceTeam],
    wanted: int,
) -> list[TileRaceTeam]:
    """Grow or shrink the event's team list to `wanted`, keeping existing identity.

    Existing teams keep their name, colour and icon; extras are created from the
    palette and surplus teams are deleted (their members fall back to the pool).
    """
    now = datetime.now(UTC)
    kept = list(teams[:wanted])
    for surplus in teams[wanted:]:
        await session.delete(surplus)
    taken = {t.slug for t in kept}
    for index in range(len(kept), wanted):
        name = f"Team {index + 1}"
        slug = slugify(name)
        while slug in taken:
            slug = f"{slug}-{index + 1}"
        taken.add(slug)
        team = TileRaceTeam(
            event_id=event_id,
            name=name,
            slug=slug,
            icon_type="item",
            icon_url="",
            color=TEAM_COLORS[index % len(TEAM_COLORS)],
            position=0,
            updated_at=now,
        )
        session.add(team)
        kept.append(team)
    await session.flush()
    return kept
