"""The public board of the active frenzy event against the real database."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import FrenzyEvent, FrenzyTemplate

pytestmark = pytest.mark.integration

_TIERS = {
    "Easy": {
        "sources": [
            {"name": "Vorkath", "hovertext": "", "icon_url": "", "items": []},
        ]
    }
}


async def _seed(engine: AsyncEngine, is_active: bool) -> None:
    now = datetime.now(UTC)
    async with AsyncSession(engine) as session:
        template = FrenzyTemplate(
            name="Board", tiers=_TIERS, created_at=now, updated_at=now
        )
        session.add(template)
        await session.flush()
        session.add(
            FrenzyEvent(
                name="Winter Frenzy",
                template_id=template.id,
                is_active=is_active,
                signups_open=True,
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()


@pytest.mark.parametrize(("is_active", "code"), [(True, 200), (False, 404)])
async def test_board_shows_only_the_active_event(
    client: AsyncClient, seed_engine: AsyncEngine, is_active: bool, code: int
) -> None:
    await _seed(seed_engine, is_active)
    resp = await client.get("/frenzy/active/board")
    assert resp.status_code == code, resp.text
    if code == 200:
        assert resp.json()["tiers"] == _TIERS
