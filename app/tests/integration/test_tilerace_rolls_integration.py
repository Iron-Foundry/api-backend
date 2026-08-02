"""Real-DB proof that the roll feed serves the whole history by default.

The endpoint used to clamp every request to 100 rows, so the web panel could
never scroll past the newest 25. These tests pin the unbounded default and the
explicit cap that still applies when a caller asks for one.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import TileRaceEvent, TileRaceRoll, TileRaceTeam
from app.tests.conftest import TEST_USER

pytestmark = pytest.mark.integration

_ROLL_COUNT = 130


async def _seed_rolls(engine: AsyncEngine) -> int:
    now = datetime.now(UTC)
    async with AsyncSession(engine) as session:
        event = TileRaceEvent(
            name="Roll History",
            is_active=False,
            cells=[],
            created_at=now,
            updated_at=now,
        )
        session.add(event)
        await session.flush()
        event_id = event.id
        team = TileRaceTeam(
            event_id=event_id,
            name="Blues",
            slug="blues",
            icon_type="npc",
            icon_url="",
            color="#00f",
            position=1,
            furthest_position=1,
            updated_at=now,
        )
        session.add(team)
        await session.flush()
        session.add_all(
            [
                TileRaceRoll(
                    event_id=event_id,
                    team_id=team.id,
                    dice=[i % 6 + 1],
                    roll=i % 6 + 1,
                    skipped=False,
                    new_position=i + 1,
                    rolled_by=int(TEST_USER["sub"]),
                    rolled_at=now - timedelta(minutes=i),
                )
                for i in range(_ROLL_COUNT)
            ]
        )
        await session.commit()
        return event_id


async def test_rolls_default_returns_full_history(
    client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    event_id = await _seed_rolls(seed_engine)

    resp = await client.get(f"/tilerace/events/{event_id}/rolls")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert len(body) == _ROLL_COUNT, "the feed was truncated below the full history"
    assert body[0]["new_position"] == 1, "the newest roll is not first"
    assert body[-1]["new_position"] == _ROLL_COUNT


async def test_rolls_limit_caps_the_page(
    client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    event_id = await _seed_rolls(seed_engine)

    resp = await client.get(f"/tilerace/events/{event_id}/rolls?limit=10")
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 10

    rejected = await client.get(f"/tilerace/events/{event_id}/rolls?limit=0")
    assert rejected.status_code == 422
