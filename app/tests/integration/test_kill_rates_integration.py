"""Staff-set kill rates, stored in Postgres and served on the loot rate routes."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx
import pytest
from httpx import AsyncClient

from app.services.osrsclans import client as osrsclans_client

pytestmark = pytest.mark.integration

_SOURCE_KEY = "Reward Chest (The Gauntlet)#Partial completion"
_RATELESS = {
    "source": _SOURCE_KEY,
    "page": "Reward Chest (The Gauntlet)",
    "section": "Partial completion",
    "category": "minigame",
    "dropTypes": ["reward"],
    "rows": 30,
    "killsPerHour": None,
    "killsPerHourIronman": None,
    "killRateSource": None,
    "womMetric": None,
    "collectionLogPage": None,
    "collectionLogRows": 0,
}


def _answer_sources(items: list[dict[str, Any]]) -> httpx.MockTransport:
    page = {"items": items, "total": len(items), "limit": 50, "offset": 0}
    return httpx.MockTransport(lambda request: httpx.Response(200, json=page))


async def _served_rate(anon: AsyncClient, q: str) -> tuple[Any, Any]:
    resp = await anon.get("/reference/loot-rates/sources", params={"q": q})
    assert resp.status_code == 200, resp.text
    source = resp.json()["items"][0]
    return source["kills_per_hour"], source["kill_rate_source"]


async def test_staff_rate_fills_source_until_removed(
    staff_client: AsyncClient,
    anon_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(osrsclans_client, "_transport", _answer_sources([_RATELESS]))
    path = f"/reference/kill-rates/{quote(_SOURCE_KEY, safe='')}"

    put = await staff_client.put(path, json={"kills_per_hour": 6.5})
    assert put.status_code == 200, put.text
    assert put.json()["source"] == _SOURCE_KEY
    assert (await anon_client.get(path)).json()["kills_per_hour"] == 6.5
    assert await _served_rate(anon_client, "Gauntlet fill") == (6.5, "foundry")

    assert (await staff_client.delete(path)).status_code == 204
    assert (await anon_client.get(path)).status_code == 404
    assert await _served_rate(anon_client, "Gauntlet unfill") == (None, None)


async def test_member_cannot_set_kill_rate(
    client: AsyncClient,
) -> None:
    resp = await client.put(
        f"/reference/kill-rates/{quote(_SOURCE_KEY, safe='')}",
        json={"kills_per_hour": 6.5},
    )
    assert resp.status_code == 403
