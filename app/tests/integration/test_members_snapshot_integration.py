"""Real-DB round trip for the member snapshot endpoint's XP and efficiency fields."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import PlayerSnapshot, User, UserAccount
from app.tests.conftest import TEST_USER

pytestmark = pytest.mark.integration

_RSN = "Some Player"


async def _seed(engine: AsyncEngine) -> None:
    now = datetime.now(UTC)
    discord_user_id = int(TEST_USER["sub"])
    async with AsyncSession(engine) as session:
        session.add(
            User(
                discord_user_id=discord_user_id,
                discord_username="TestUser",
                created_at=now,
            )
        )
        session.add(
            UserAccount(
                discord_user_id=discord_user_id,
                rsn=_RSN,
                is_primary=True,
                created_at=now,
            )
        )
        session.add(
            PlayerSnapshot(
                rsn=_RSN.lower(),
                skills={"overall": 346368.0, "slayer": 40.0},
                bosses={"zulrah": 1204},
                activities={"clue_scrolls_all": 12},
                ehp=1104.7,
                ehb=946.2,
                fetched_at=now,
            )
        )
        await session.commit()


async def test_snapshot_returns_overall_xp_and_efficiency(
    client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    await _seed(seed_engine)

    resp = await client.get("/members/me/snapshot")

    assert resp.status_code == 200
    body = resp.json()
    assert body["rsn"] == _RSN
    assert body["skills"]["overall"] == 346368.0
    assert body["ehp"] == 1104.7
    assert body["ehb"] == 946.2
