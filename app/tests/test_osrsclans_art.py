"""The `/reference/osrs/npcs` and `/reference/osrs/sprites` routes."""

from __future__ import annotations

import httpx
import pytest
from httpx import AsyncClient

from app.services.osrsclans import client

# Trimmed live rows from https://osrsclans.cc/api/v1/osrs/{npcs,sprites}/search
_NPCS = {
    "items": [{"id": 2042, "name": "Zulrah", "combatLevel": 725, "size": 5}],
    "total": 3,
    "limit": 20,
    "offset": 0,
}
_SPRITES = {
    "items": [{"id": 4255, "name": "Slayer", "category": "IconStat50x50"}],
    "total": 22,
    "limit": 20,
    "offset": 0,
}


@pytest.mark.parametrize(
    ("path", "answer", "upstream", "image"),
    [
        ("npcs", _NPCS, "/api/v1/osrs/npcs/search", "/npcs/2042.webp"),
        ("sprites", _SPRITES, "/api/v1/osrs/sprites/search", "/sprites/4255.webp"),
    ],
)
async def test_search_answers_rows_with_image_urls(
    anon_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    answer: dict[str, object],
    upstream: str,
    image: str,
) -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=answer)

    monkeypatch.setattr(client, "_transport", httpx.MockTransport(handle))
    resp = await anon_client.get(f"/reference/osrs/{path}?q=zul&limit=5")

    assert resp.status_code == 200, resp.text
    row = resp.json()["items"][0]
    assert row["image_url"] == f"https://api.test/reference/osrs/images{image}"
    assert (seen[0].url.path, seen[0].url.params["q"]) == (upstream, "zul")


async def test_npc_rows_answer_snake_case(
    anon_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        client,
        "_transport",
        httpx.MockTransport(lambda r: httpx.Response(200, json=_NPCS)),
    )
    row = (await anon_client.get("/reference/osrs/npcs?q=zulrah")).json()["items"][0]
    assert (row["name"], row["combat_level"]) == ("Zulrah", 725)


@pytest.mark.parametrize(
    "query",
    ["npcs", "npcs?q=z", "npcs?q=" + "z" * 65, "npcs?q=zul&limit=51", "sprites?q=s"],
)
async def test_search_refuses_out_of_bound_queries(
    anon_client: AsyncClient, query: str
) -> None:
    assert (await anon_client.get(f"/reference/osrs/{query}")).status_code == 422
