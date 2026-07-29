"""Importing a playlist link as a saved playlist.

Lavalink is stubbed with a transport rather than reached. What matters is that
the whole playlist comes across rather than a search-sized page of it, that it
takes the source's own name, and that a link which resolves to nothing says so
instead of creating an empty playlist.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from httpx import AsyncClient

from app.services import lavalink
from app.services.lavalink import IMPORT_LIMIT, load

SPOTIFY_LINK = "https://open.spotify.com/playlist/abc123"


def track(index: int) -> dict[str, Any]:
    return {
        "encoded": f"QAAA{index}",
        "info": {
            "identifier": f"id{index}",
            "author": "Barbarian Assault",
            "length": 180_000,
            "isStream": False,
            "title": f"Track {index}",
            "uri": f"https://open.spotify.com/track/id{index}",
            "artworkUrl": None,
            "isrc": f"USABC123456{index}",
            "sourceName": "spotify",
        },
    }


def playlist_body(count: int, name: str = "Slayer Tunes") -> dict[str, Any]:
    return {
        "loadType": "playlist",
        "data": {
            "info": {"name": name, "selectedTrack": -1},
            "pluginInfo": {},
            "tracks": [track(i) for i in range(count)],
        },
    }


def answering(body: Any, status: int = 200) -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(status, json=body))


@pytest.fixture(autouse=True)
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lavalink, "LAVALINK_URI", "http://lavalink.invalid")
    monkeypatch.setattr(lavalink, "LAVALINK_PASSWORD", "shhh")


async def test_a_playlist_link_keeps_its_name() -> None:
    result = await load(SPOTIFY_LINK, transport=answering(playlist_body(3)))

    assert result.playlist_name == "Slayer Tunes"
    assert len(result.tracks) == 3


async def test_a_search_has_no_playlist_name() -> None:
    body = {"loadType": "search", "data": [track(0)]}
    result = await load("zanaris", transport=answering(body))

    assert result.playlist_name is None


async def test_an_import_takes_far_more_than_a_search_page() -> None:
    # A search shows 25; an import must not silently truncate a real playlist
    # to the same page.
    result = await load(
        SPOTIFY_LINK, limit=IMPORT_LIMIT, transport=answering(playlist_body(120))
    )

    assert len(result.tracks) == 120
    assert IMPORT_LIMIT >= 500


async def test_an_import_stops_at_what_a_playlist_may_hold() -> None:
    result = await load(
        SPOTIFY_LINK, limit=IMPORT_LIMIT, transport=answering(playlist_body(700))
    )

    assert len(result.tracks) == IMPORT_LIMIT


async def test_importing_requires_a_login(anon_client: AsyncClient) -> None:
    response = await anon_client.post(
        "/music/playlists/import", json={"url": SPOTIFY_LINK}
    )
    assert response.status_code == 401


async def test_something_that_is_not_a_link_is_refused(
    auth_client: AsyncClient, mock_session: MagicMock
) -> None:
    response = await auth_client.post(
        "/music/playlists/import", json={"url": "slayer tunes"}
    )

    assert response.status_code == 422
    mock_session.add.assert_not_called()


async def test_a_link_that_loads_nothing_creates_no_playlist(
    auth_client: AsyncClient, mock_session: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def nothing(*args: Any, **kwargs: Any) -> lavalink.LoadResult:
        return lavalink.LoadResult()

    monkeypatch.setattr("app.routers.music.importing.load", nothing)

    response = await auth_client.post(
        "/music/playlists/import", json={"url": SPOTIFY_LINK}
    )

    assert response.status_code == 404
    mock_session.add.assert_not_called()


async def test_import_is_unavailable_without_a_node(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(lavalink, "LAVALINK_URI", "")

    response = await auth_client.post(
        "/music/playlists/import", json={"url": SPOTIFY_LINK}
    )
    assert response.status_code == 503


async def test_the_import_path_is_not_read_as_a_playlist_id(
    auth_client: AsyncClient,
) -> None:
    # `/playlists/{playlist_id}` would otherwise try to parse "import" as an int.
    response = await auth_client.post(
        "/music/playlists/import", json={"url": "not-a-link"}
    )

    assert response.status_code == 422
    assert "link" in response.json()["detail"]
