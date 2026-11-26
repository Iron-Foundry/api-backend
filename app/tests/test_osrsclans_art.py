"""The `/reference/osrs/npcs` and `/reference/osrs/sprites` name searches."""

from __future__ import annotations

import httpx
import pytest
from httpx import AsyncClient

from app.services.osrsclans import client

# Trimmed live shapes of https://osrsclans.cc/api/v1/osrs/npcs/names and /osrs/sprites
_NPC_NAMES = {
    "2042": "Zulrah",
    "2043": "Zulrah",
    "6766": "K'ril Tsutsaroth",
    "1": "Imp",
}
_SPRITES = {
    "items": [
        {"id": 4255, "name": "Slayer", "category": "IconStat50x50"},
        {"id": 216, "name": "SLAYER", "category": "Staticons2"},
        {"id": 3206, "name": "Slayer Master", "category": "ClanRankIcons"},
    ],
    "total": 3,
    "limit": 500,
    "offset": 0,
}


def _serving(seen: list[httpx.Request]) -> httpx.MockTransport:
    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = _NPC_NAMES if request.url.path.endswith("/names") else _SPRITES
        return httpx.Response(200, json=body)

    return httpx.MockTransport(answer)


async def test_npc_search_matches_without_punctuation(
    anon_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[httpx.Request] = []
    monkeypatch.setattr(client, "_transport", _serving(seen))

    resp = await anon_client.get("/reference/osrs/npcs?q=kril")

    assert resp.status_code == 200, resp.text
    rows = resp.json()["items"]
    assert [(r["id"], r["name"]) for r in rows] == [(6766, "K'ril Tsutsaroth")]
    assert (
        rows[0]["image_url"] == "https://api.test/reference/osrs/images/npcs/6766.webp"
    )
    assert seen[0].url.path == "/api/v1/osrs/npcs/names"


async def test_searches_reuse_the_name_index(
    anon_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[httpx.Request] = []
    monkeypatch.setattr(client, "_transport", _serving(seen))

    await anon_client.get("/reference/osrs/npcs?q=zul")
    await anon_client.get("/reference/osrs/npcs?q=imp")

    assert len(seen) == 1


async def test_sprite_search_ranks_the_exact_name_first(
    anon_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(client, "_transport", _serving([]))

    resp = await anon_client.get("/reference/osrs/sprites?q=slayer&limit=2")

    page = resp.json()
    assert [r["id"] for r in page["items"]] == [216, 4255]
    assert page["total"] == 3
    assert page["items"][0]["category"] == "Staticons2"


@pytest.mark.parametrize(
    "query",
    ["npcs", "npcs?q=z", "npcs?q=" + "z" * 65, "npcs?q=zul&limit=51", "sprites?q=s"],
)
async def test_search_refuses_out_of_bound_queries(
    anon_client: AsyncClient, query: str
) -> None:
    assert (await anon_client.get(f"/reference/osrs/{query}")).status_code == 422
