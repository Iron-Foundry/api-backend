"""A signed-out visitor reads a stored member avatar, for the Our Team page."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import User

pytestmark = pytest.mark.integration

_STAFF_ID = 515151
_AVATAR = "https://cdn.discordapp.com/avatars/515151/abc.png"


async def test_signed_out_visitor_reads_avatar(
    anon_client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    async with AsyncSession(seed_engine) as session:
        session.add(
            User(
                discord_user_id=_STAFF_ID,
                discord_username="staffer",
                discord_avatar_url=_AVATAR,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        await session.commit()

    resp = await anon_client.get(f"/members/{_STAFF_ID}/avatar")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"avatar_url": _AVATAR}
