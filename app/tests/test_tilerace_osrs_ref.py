"""The tile editor's NPC search: names from our own cache, artwork from the wiki.

Mocks replace `httpx` inside `app.routers.tilerace.osrs_ref`'s own module namespace
rather than the shared module object, because the test client is itself an
`httpx.AsyncClient` and patching the real class would hijack its request to the app.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from httpx import AsyncClient, Response

from app.routers.tilerace import osrs_ref

_VORKATH_ROWS = [
    {"npc_id": 8026, "name": "Vorkath", "combat_level": 0},
    {"npc_id": 8060, "name": "Vorkath", "combat_level": 392},
    {"npc_id": 8061, "name": "Vorkath", "combat_level": 732},
    {"npc_id": 9999, "name": "", "combat_level": 0},
]


def _fake_httpx(rows: Any) -> MagicMock:
    # raise_for_status() needs the originating request, which a bare Response lacks.
    request = httpx.Request("GET", "http://osrs-cache-service:8100/npcs")
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(return_value=Response(200, json=rows, request=request))
    module = MagicMock()
    module.AsyncClient = MagicMock(return_value=client)
    return module


def _fake_wiki(thumbnails: dict[str, str] | Exception) -> MagicMock:
    handler = MagicMock()
    handler.__aenter__ = AsyncMock(return_value=handler)
    handler.__aexit__ = AsyncMock(return_value=False)
    if isinstance(thumbnails, Exception):
        handler.get_page_thumbnails = AsyncMock(side_effect=thumbnails)
    else:
        handler.get_page_thumbnails = AsyncMock(return_value=thumbnails)
    return MagicMock(return_value=handler)


async def test_osrs_npcs_collapses_forms_to_the_fightable_one(
    auth_client: AsyncClient,
) -> None:
    icon = "https://oldschool.runescape.wiki/images/thumb/Vorkath.png"
    with (
        patch.object(osrs_ref, "httpx", _fake_httpx(_VORKATH_ROWS)),
        patch.object(osrs_ref, "OsrsWikiContentHandler", _fake_wiki({"Vorkath": icon})),
    ):
        resp = await auth_client.get("/tilerace/osrs/npcs?q=vorkath")

    assert resp.status_code == 200
    assert resp.json() == [{"id": 8061, "name": "Vorkath", "icon_url": icon}]


async def test_osrs_npcs_keeps_names_when_the_wiki_has_no_artwork(
    auth_client: AsyncClient,
) -> None:
    """The 2026 loss of the wiki's cargoquery API emptied this search entirely.

    Artwork is the wiki's job and names are ours, so a wiki failure must cost the
    picture and nothing else.
    """
    with (
        patch.object(osrs_ref, "httpx", _fake_httpx(_VORKATH_ROWS)),
        patch.object(
            osrs_ref, "OsrsWikiContentHandler", _fake_wiki(httpx.RequestError("down"))
        ),
    ):
        resp = await auth_client.get("/tilerace/osrs/npcs?q=vorkath")

    assert resp.status_code == 200
    assert resp.json() == [{"id": 8061, "name": "Vorkath", "icon_url": ""}]


async def test_osrs_npcs_ranks_prefix_matches_first(auth_client: AsyncClient) -> None:
    rows = [
        {"npc_id": 1, "name": "Giant rat", "combat_level": 3},
        {"npc_id": 2, "name": "Ratcatcher", "combat_level": 0},
        {"npc_id": 3, "name": "Rat", "combat_level": 1},
    ]
    with (
        patch.object(osrs_ref, "httpx", _fake_httpx(rows)),
        patch.object(osrs_ref, "OsrsWikiContentHandler", _fake_wiki({})),
    ):
        resp = await auth_client.get("/tilerace/osrs/npcs?q=rat")

    assert [row["name"] for row in resp.json()] == ["Rat", "Ratcatcher", "Giant rat"]


async def test_osrs_npcs_empty_when_the_cache_service_is_down(
    auth_client: AsyncClient,
) -> None:
    module = _fake_httpx([])
    module.AsyncClient.return_value.get = AsyncMock(
        side_effect=httpx.RequestError("unreachable")
    )
    with patch.object(osrs_ref, "httpx", module):
        resp = await auth_client.get("/tilerace/osrs/npcs?q=vorkath")

    assert resp.status_code == 200
    assert resp.json() == []
