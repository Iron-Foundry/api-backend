"""The tile editor's NPC search, on the OSRSClans NPC search and its stills."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from httpx import AsyncClient

from app.services.osrsclans import client as osrsclans_client


def _page(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"items": rows, "total": len(rows), "limit": 100, "offset": 0}


def _answer(monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, Any]]) -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json=_page(rows)))
    monkeypatch.setattr(osrsclans_client, "_transport", transport)


async def test_npc_search_keeps_the_fightable_form(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _answer(
        monkeypatch,
        [
            {"id": 8026, "name": "Vorkath", "combatLevel": None},
            {"id": 8061, "name": "Vorkath", "combatLevel": 732},
            {"id": 8060, "name": "Vorkath", "combatLevel": 392},
        ],
    )

    resp = await auth_client.get("/tilerace/osrs/npcs?q=vorkath")

    assert resp.status_code == 200, resp.text
    assert resp.json() == [
        {
            "id": 8061,
            "name": "Vorkath",
            "icon_url": "https://osrsclans.cc/api/v1/osrs/npcs/8061.webp",
        }
    ]


async def test_npc_search_ranks_prefix_matches_first(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _answer(
        monkeypatch,
        [
            {"id": 1, "name": "Giant rat", "combatLevel": 3},
            {"id": 2, "name": "Ratcatcher", "combatLevel": None},
            {"id": 3, "name": "Rat", "combatLevel": 1},
        ],
    )

    resp = await auth_client.get("/tilerace/osrs/npcs?q=rat")

    assert [row["name"] for row in resp.json()] == ["Rat", "Ratcatcher", "Giant rat"]


async def test_npc_search_reports_osrsclans_down_as_502(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(503, json={}))
    monkeypatch.setattr(osrsclans_client, "_transport", transport)

    resp = await auth_client.get("/tilerace/osrs/npcs?q=vorkath")

    assert resp.status_code == 502
