"""The public list of the active frenzy event's signups, against the real database."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from app.tests.integration._frenzy_draft_seed import POOL, seed_event

pytestmark = pytest.mark.integration


async def test_signups_list_strongest_first_with_rank(
    anon_client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    await seed_event(seed_engine)

    resp = await anon_client.get("/frenzy/active/signups")

    assert resp.status_code == 200, resp.text
    members = resp.json()["members"]
    assert [m["rsn"] for m in members] == [*POOL, "Cap A", "Cap B"]
    assert (members[0]["rank"], members[0]["points"], members[0]["timezone"]) == (
        "Ruby",
        600,
        "Asia/Kolkata",
    )
    assert members[-1]["rank"] is None


async def test_signups_need_an_active_event(anon_client: AsyncClient) -> None:
    assert (await anon_client.get("/frenzy/active/signups")).status_code == 404
