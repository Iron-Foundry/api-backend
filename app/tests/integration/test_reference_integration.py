"""Real-DB persistence and read-back for the reference rates endpoint."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.services.efficiency_rates._parse import RateRow
from app.services.efficiency_rates._repository import store_rates

pytestmark = pytest.mark.integration


async def test_rates_round_trip(client: AsyncClient, seed_engine: AsyncEngine) -> None:
    async with AsyncSession(seed_engine) as session:
        await store_rates(
            session,
            [
                RateRow("zulrah", "ehb", 45.0),
                RateRow("ranged", "ehp", 842800.0, {"methods": []}),
            ],
        )

    resp = await client.get("/reference/rates?kind=ehb")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert any(r["metric"] == "zulrah" and r["rate"] == 45.0 for r in body)
