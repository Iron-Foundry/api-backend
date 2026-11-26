"""The OSRSClans loot rate client and the `/reference/loot-rates` route."""

from __future__ import annotations

import json
from typing import Any, get_args
from unittest.mock import AsyncMock

import httpx
import pytest
from httpx import AsyncClient

from app.services.osrsclans import client
from app.services.osrsclans.client import cache_key
from app.services.osrsclans.loot_rate_models import KillRateSource
from app.services.osrsclans.loot_rates import LootRateAsk, LootSourceAsk

# One live row from https://osrsclans.cc/api/v1/loot-rates?q=Spirit%20seed
_ROW = {
    "itemId": 5317,
    "itemName": "Spirit seed",
    "source": "Tormented Demon",
    "page": "Tormented Demon",
    "section": None,
    "category": "monster",
    "dropType": "combat",
    "group": "Seeds",
    "lines": [
        {
            "rarity": "1/1,593.7",
            "altRarity": None,
            "rolls": 1.0,
            "quantity": "1",
            "quantityLow": 1.0,
            "quantityHigh": 1.0,
            "noted": False,
            "approximate": True,
            "group": "Seeds",
        }
    ],
    "chance": 0.0006274706657464213,
    "altChance": None,
    "perPurple": False,
    "uniquesPerRaid": None,
    "chancePerRaid": None,
    "killsPerHour": 44.4,
    "killsPerHourIronman": None,
    "killRateSource": "droptracker",
    "womMetric": None,
    "skill": None,
    "gePrice": None,
    "highAlchemy": None,
    "collectionLog": False,
    "collectionLogPage": None,
    "readAt": "2026-11-25T04:33:22.443951Z",
}
_PAGE = {"items": [_ROW], "total": 1, "limit": 1, "offset": 0}


def _answering(
    body: Any, status: int, seen: list[httpx.Request]
) -> httpx.MockTransport:
    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body)

    return httpx.MockTransport(answer)


def test_cache_key_ignores_order_and_unset() -> None:
    first = LootRateAsk(item=5317, q="seed", limit=10)
    second = LootRateAsk(q="seed", limit=10, item=5317, source=None)
    assert cache_key(first) == cache_key(second)
    assert "source" not in cache_key(first)
    assert cache_key(LootRateAsk(page="Vorkath")) != cache_key(
        LootSourceAsk(page="Vorkath")
    )


async def test_route_answers_snake_case_and_caches(
    anon_client: AsyncClient, mock_valkey: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[httpx.Request] = []
    monkeypatch.setattr(client, "_transport", _answering(_PAGE, 200, seen))

    resp = await anon_client.get("/reference/loot-rates?q=Spirit seed&limit=1")

    assert resp.status_code == 200, resp.text
    row = resp.json()["items"][0]
    assert (row["item_id"], row["group"], row["kill_rate_source"]) == (
        5317,
        "Seeds",
        "droptracker",
    )
    assert row["lines"][0]["quantity_high"] == 1.0
    assert row["image_url"] == "https://api.test/reference/osrs/images/items/5317.webp"
    assert seen[0].url.path == "/api/v1/loot-rates"
    key, cached = mock_valkey.set.await_args.args
    assert key == cache_key(LootRateAsk(q="Spirit seed", limit=1))
    assert json.loads(cached)["items"][0]["item_name"] == "Spirit seed"


async def test_route_sends_filters_in_camel_case(
    anon_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[httpx.Request] = []
    monkeypatch.setattr(client, "_transport", _answering(_PAGE, 200, seen))
    query = "page=Ancient chest&category=raid&wom_metric=chambers_of_xeric"
    query += "&points=30000&raid_level=300"

    assert (await anon_client.get(f"/reference/loot-rates?{query}")).status_code == 200

    sent = seen[0].url.params
    assert (sent["page"], sent["category"], sent["womMetric"]) == (
        "Ancient chest",
        "raid",
        "chambers_of_xeric",
    )
    assert (sent["points"], sent["raidLevel"]) == ("30000", "300")


async def test_route_serves_a_cached_copy_without_fetching(
    anon_client: AsyncClient, mock_valkey: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[httpx.Request] = []
    monkeypatch.setattr(client, "_transport", _answering(_PAGE, 200, seen))
    mock_valkey.get.return_value = json.dumps(_PAGE).encode()

    resp = await anon_client.get("/reference/loot-rates?item=5317")

    assert resp.status_code == 200, resp.text
    assert resp.json()["items"][0]["read_at"].startswith("2026-11-25T04:33:22")
    assert seen == []


@pytest.mark.parametrize("measurer", get_args(KillRateSource))
async def test_route_passes_every_kill_rate_source(
    anon_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, measurer: str
) -> None:
    page = {**_PAGE, "items": [{**_ROW, "killRateSource": measurer}]}
    monkeypatch.setattr(client, "_transport", _answering(page, 200, []))
    resp = await anon_client.get("/reference/loot-rates")
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"][0]["kill_rate_source"] == measurer
