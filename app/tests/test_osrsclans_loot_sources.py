"""The `/reference/loot-rates/sources` route, the failures that all OSRSClans
routes share, and the query bounds of both loot rate routes."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import httpx
import pytest
from httpx import AsyncClient

from app.services.osrsclans import client
from app.services.osrsclans.client import cache_key
from app.services.osrsclans.loot_rates import LootSourceAsk

_OSRSCLANS_ROUTES = [
    "/reference/loot-rates",
    "/reference/loot-rates/sources",
    "/reference/loot-rates/collection-log?name=Vorkath",
    "/reference/osrs/npcs?q=zulrah",
    "/reference/osrs/sprites?q=slayer",
]

# One live row from https://osrsclans.cc/api/v1/loot-rates/sources?page=Vorkath
_SOURCE = {
    "source": "Vorkath#Post-quest",
    "page": "Vorkath",
    "section": "Post-quest",
    "category": "boss",
    "dropTypes": ["combat"],
    "rows": 84,
    "killsPerHour": 34.0,
    "killsPerHourIronman": 34.0,
    "killRateSource": "wom",
    "womMetric": "vorkath",
    "collectionLogPage": "Vorkath",
    "collectionLogRows": 6,
}
_PAGE = {"items": [_SOURCE], "total": 1, "limit": 50, "offset": 0}


async def test_sources_answer_snake_case_and_cache(
    anon_client: AsyncClient, mock_valkey: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_PAGE)

    monkeypatch.setattr(client, "_transport", httpx.MockTransport(answer))

    resp = await anon_client.get(
        "/reference/loot-rates/sources?category=boss&wom_metric=vorkath"
    )

    assert resp.status_code == 200, resp.text
    source = resp.json()["items"][0]
    assert (source["source"], source["drop_types"], source["wom_metric"]) == (
        "Vorkath#Post-quest",
        ["combat"],
        "vorkath",
    )
    assert seen[0].url.path == "/api/v1/loot-rates/sources"
    assert seen[0].url.params["womMetric"] == "vorkath"
    key, cached = mock_valkey.set.await_args.args
    assert key == cache_key(LootSourceAsk(category="boss", wom_metric="vorkath"))
    assert json.loads(cached)["items"][0]["rows"] == 84


@pytest.mark.parametrize("status", [404, 500, 503])
@pytest.mark.parametrize("path", _OSRSCLANS_ROUTES)
async def test_routes_report_osrsclans_failure_as_502(
    anon_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, status: int, path: str
) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={})

    monkeypatch.setattr(client, "_transport", httpx.MockTransport(fail))
    resp = await anon_client.get(path)
    assert resp.status_code == 502
    assert str(status) in resp.json()["detail"]


@pytest.mark.parametrize("path", _OSRSCLANS_ROUTES)
async def test_routes_report_unreachable_osrsclans_as_502(
    anon_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    monkeypatch.setattr(client, "_transport", httpx.MockTransport(refuse))
    resp = await anon_client.get(path)
    assert resp.status_code == 502


@pytest.mark.parametrize(
    "query",
    [
        "?item=-1",
        "?level=0",
        "?level=100",
        "?points=3420001",
        "?raid_level=601",
        "?category=bogus",
        "?limit=501",
        "?q=x",
        "?q=" + "x" * 65,
        "/sources?category=bogus",
        "/sources?q=x",
        "/sources?limit=501",
        "/collection-log",
        "/collection-log?name=x",
    ],
)
async def test_routes_refuse_out_of_bound_filters(
    anon_client: AsyncClient, query: str
) -> None:
    assert (await anon_client.get(f"/reference/loot-rates{query}")).status_code == 422
