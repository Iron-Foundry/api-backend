"""The asset manager's OSRSClans routes and the shapes they map answers to."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from httpx import AsyncClient

from app.services.osrsclans import client as osrsclans_client

_OSRS = "https://api.test/reference/osrs/images"
_COINS = {
    "id": 995,
    "name": "Coins",
    "stackable": True,
    "placeholderId": 14440,
    "stackForms": [{"amount": 2, "itemId": 996}],
}
_SPRITE = {
    "id": 197,
    "name": "ATTACK",
    "category": "Staticons",
    "frames": [
        {"frame": 0, "width": 25, "height": 25, "empty": False},
        {"frame": 1, "width": 0, "height": 0, "empty": True},
    ],
}


def _answer(monkeypatch: pytest.MonkeyPatch, routes: dict[str, Any]) -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        body = routes.get(request.url.path.removeprefix("/api/v1"))
        return (
            httpx.Response(404, json={})
            if body is None
            else httpx.Response(200, json=body)
        )

    monkeypatch.setattr(osrsclans_client, "_transport", httpx.MockTransport(answer))


def _page(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"items": items, "total": len(items), "limit": 50, "offset": 0}


async def test_item_list_skips_forms_without_a_name(
    anon_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _answer(monkeypatch, {"/osrs/items": _page([_COINS, {"id": 996, "name": None}])})

    body = (await anon_client.get("/reference/osrs/items")).json()

    assert [(i["item_id"], i["icon_url"], i["variant_count"]) for i in body] == [
        (995, f"{_OSRS}/items/995.webp", 3)
    ]


async def test_variants_name_each_form_after_the_item(
    anon_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _answer(monkeypatch, {"/osrs/items/995": _COINS})

    body = (await anon_client.get("/reference/osrs/items/995/variants")).json()

    assert [(i["item_id"], i["name"]) for i in body] == [
        (995, "Coins"),
        (14440, "Coins (placeholder)"),
        (996, "Coins x2"),
    ]


async def test_unknown_item_answers_404(
    anon_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _answer(monkeypatch, {})
    assert (await anon_client.get("/reference/osrs/items/9999999")).status_code == 404


async def test_sprite_frames_skip_empty_frames(
    anon_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _answer(monkeypatch, {"/osrs/sprites": _page([_SPRITE])})

    body = (
        await anon_client.get("/reference/osrs/sprite-frames?category=Staticons")
    ).json()

    frames = [(f["sprite_id"], f["frame_index"], f["webp_url"]) for f in body["items"]]
    assert frames == [(197, 0, f"{_OSRS}/sprites/197.webp?frame=0")]
    assert body["sprites"] == 1


async def test_sprite_categories_drop_the_uncategorised(
    anon_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    categories = [
        {"category": None, "sprites": 1150},
        {"category": "Staticons", "sprites": 18},
    ]
    _answer(monkeypatch, {"/osrs/sprites/categories": categories})

    body = (await anon_client.get("/reference/osrs/sprites/categories")).json()

    assert body == [{"category": "Staticons", "count": 18}]
