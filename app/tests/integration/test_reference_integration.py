"""Real-DB persistence + read-back for the reference loot and rates endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.services.efficiency_rates._parse import RateRow
from app.services.efficiency_rates._repository import store_rates
from app.services.loot_tables._catalog import LootSourceEntry
from app.services.loot_tables._drops import ParsedDrop
from app.services.loot_tables._repository import prune_sources, store_source_drops

pytestmark = pytest.mark.integration

_ENTRY = LootSourceEntry("zulrah", "Zulrah", "boss", "Zulrah")
_DROPS = [
    ParsedDrop("Tanzanite fang", 1, 1, False, 1, 1024, None, 2, "Uniques"),
    ParsedDrop("Zulrah's scales", 100, 299, False, 1, 1, None, 1, "100%"),
]
_ITEM_INDEX = {"tanzanite fang": 12934, "zulrah's scales": 12934}


@pytest.fixture(autouse=True)
def _no_prices(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import AsyncMock

    monkeypatch.setattr(
        "app.routers.reference.loot.prices_for", AsyncMock(return_value={})
    )


async def _seed(engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as session:
        await store_source_drops(session, _ENTRY, _DROPS, _ITEM_INDEX)
        await store_rates(
            session,
            [
                RateRow("zulrah", "ehb", 45.0),
                RateRow("ranged", "ehp", 842800.0, {"methods": []}),
            ],
        )


async def test_loot_source_round_trip(
    client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    await _seed(seed_engine)

    listed = await client.get("/reference/loot/sources?category=boss")
    assert listed.status_code == 200, listed.text
    zulrah = next(s for s in listed.json() if s["slug"] == "zulrah")
    assert zulrah["drop_count"] == 2

    detail = await client.get("/reference/loot/sources/zulrah")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert {d["item_name"] for d in body["drops"]} == {
        "Tanzanite fang",
        "Zulrah's scales",
    }


async def test_item_reverse_lookup(
    client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    await _seed(seed_engine)

    resp = await client.get("/reference/loot/items/12934")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body
    assert body[0]["source"]["slug"] == "zulrah"


async def test_rates_round_trip(client: AsyncClient, seed_engine: AsyncEngine) -> None:
    await _seed(seed_engine)

    resp = await client.get("/reference/rates?kind=ehb")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert any(r["metric"] == "zulrah" and r["rate"] == 45.0 for r in body)


async def test_prune_removes_sources_absent_from_catalog(
    client: AsyncClient, seed_engine: AsyncEngine
) -> None:
    stale = LootSourceEntry("chambers_of_xeric_challenge_mode", "CoX CM", "boss", "x")
    async with AsyncSession(seed_engine) as session:
        await store_source_drops(session, _ENTRY, _DROPS, _ITEM_INDEX)
        await store_source_drops(session, stale, [], _ITEM_INDEX)
        await prune_sources(session, {"zulrah"})

    listed = await client.get("/reference/loot/sources")
    slugs = {s["slug"] for s in listed.json()}
    assert "zulrah" in slugs
    assert "chambers_of_xeric_challenge_mode" not in slugs
