"""The `/reference/loot-rates/collection-log` route over the OSRSClans flag."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from httpx import AsyncClient

from app.services.osrsclans import client

_COX = "Chambers of Xeric"


def _source(key: str, page: str) -> dict[str, Any]:
    return {
        "source": key,
        "page": key.split("#")[0],
        "section": None,
        "category": "raid",
        "dropTypes": ["reward"],
        "rows": 40,
        "killsPerHour": 2.0,
        "killsPerHourIronman": None,
        "killRateSource": "wom",
        "womMetric": None,
        "collectionLogPage": page,
        "collectionLogRows": 2,
    }


def _row(item: str, source: str, page: str) -> dict[str, Any]:
    return {
        "itemId": 1,
        "itemName": item,
        "source": source,
        "page": source.split("#")[0],
        "section": None,
        "category": "raid",
        "dropType": "reward",
        "group": None,
        "lines": [],
        "chance": 0.01,
        "altChance": None,
        "perPurple": True,
        "uniquesPerRaid": None,
        "chancePerRaid": 0.02,
        "killsPerHour": 2.0,
        "killsPerHourIronman": None,
        "killRateSource": "wom",
        "womMetric": None,
        "skill": None,
        "gePrice": None,
        "highAlchemy": None,
        "collectionLog": True,
        "collectionLogPage": page,
        "readAt": "2026-11-26T04:00:00Z",
    }


_SOURCE_PAGES = {
    "0": [_source("Ancient chest#Normal Mode", _COX), _source("Kraken", "Kraken")],
    "500": [_source("Ancient chest#Challenge Mode", _COX)],
}


def _answer(request: httpx.Request, seen: list[str]) -> httpx.Response:
    params = request.url.params
    if request.url.path.endswith("/sources"):
        items = _SOURCE_PAGES[params["offset"]]
        return httpx.Response(
            200, json={"items": items, "total": 501, "limit": 500, "offset": 0}
        )
    source = params["source"]
    seen.append(source)
    rows = [_row("Twisted bow", source, _COX), _row("Tormented synapse", source, "X")]
    return httpx.Response(
        200, json={"items": rows, "total": 2, "limit": 100, "offset": 0}
    )


async def test_collection_log_gathers_every_source_of_page(
    anon_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []
    transport = httpx.MockTransport(lambda request: _answer(request, seen))
    monkeypatch.setattr(client, "_transport", transport)

    resp = await anon_client.get(
        "/reference/loot-rates/collection-log?name=chambers of xeric"
    )

    assert resp.status_code == 200, resp.text
    assert sorted(seen) == ["Ancient chest#Challenge Mode", "Ancient chest#Normal Mode"]
    rows = resp.json()["items"]
    assert {(r["item_name"], r["collection_log_page"]) for r in rows} == {
        ("Twisted bow", _COX)
    }
    assert len(rows) == 2
