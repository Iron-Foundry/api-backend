"""Resolving a query into something queueable or savable.

Lavalink is stubbed with an httpx transport rather than reached: what matters
here is that each load result shape flattens into the same list, that a refusal
becomes a readable error, and that a search never needs a session - which is
what lets a playlist be built with nothing playing.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from httpx import AsyncClient

from app.services import lavalink
from app.services.lavalink import SearchError, build_identifier, load_tracks

TRACK_INFO: dict[str, Any] = {
    "identifier": "abc123",
    "isSeekable": True,
    "author": "Barbarian Assault",
    "length": 180_000,
    "isStream": False,
    "position": 0,
    "title": "Zanaris Nocturne",
    "uri": "https://open.spotify.com/track/abc123",
    "artworkUrl": "https://art.invalid/a.png",
    "isrc": "USABC1234567",
    "sourceName": "spotify",
}
TRACK = {"encoded": "QAAA", "info": TRACK_INFO, "pluginInfo": {}, "userData": {}}


def answering(body: Any, status: int = 200) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handle)


@pytest.fixture(autouse=True)
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lavalink, "LAVALINK_URI", "http://lavalink.invalid")
    monkeypatch.setattr(lavalink, "LAVALINK_PASSWORD", "shhh")


def test_a_search_is_prefixed_for_the_source_it_names() -> None:
    assert build_identifier("sea shanty", "youtube") == "ytsearch:sea shanty"
    assert build_identifier("sea shanty", "soundcloud") == "scsearch:sea shanty"


def test_a_link_is_loaded_as_itself() -> None:
    # Prefixing a URL would search for the text of the link instead of loading it.
    link = "https://open.spotify.com/track/abc123"
    assert build_identifier(link, "youtube") == link


async def test_a_search_result_flattens_into_tracks() -> None:
    found = await load_tracks(
        "zanaris", transport=answering({"loadType": "search", "data": [TRACK]})
    )

    assert len(found) == 1
    assert found[0]["title"] == "Zanaris Nocturne"
    assert found[0]["duration_ms"] == 180_000
    assert found[0]["isrc"] == "USABC1234567"
    assert found[0]["source"] == "spotify"


async def test_a_single_track_result_flattens_the_same_way() -> None:
    found = await load_tracks(
        "https://x.invalid/t", transport=answering({"loadType": "track", "data": TRACK})
    )

    assert [track["title"] for track in found] == ["Zanaris Nocturne"]


async def test_a_playlist_link_comes_back_as_its_tracks() -> None:
    body = {
        "loadType": "playlist",
        "data": {"info": {"name": "Slayer"}, "tracks": [TRACK, TRACK]},
    }
    found = await load_tracks("https://x.invalid/p", transport=answering(body))

    assert len(found) == 2


async def test_nothing_found_is_an_empty_list_not_an_error() -> None:
    found = await load_tracks(
        "asdfghjkl", transport=answering({"loadType": "empty", "data": None})
    )

    assert found == []


async def test_a_load_error_is_reported_as_one() -> None:
    body = {"loadType": "error", "data": {"message": "no such video", "severity": "c"}}
    with pytest.raises(SearchError, match="no such video"):
        await load_tracks("x", transport=answering(body))


async def test_a_refusal_from_lavalink_becomes_a_readable_error() -> None:
    with pytest.raises(SearchError):
        await load_tracks("x", transport=answering({}, status=401))


async def test_an_unreachable_node_does_not_raise_a_transport_error() -> None:
    def explode(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(SearchError, match="not reachable"):
        await load_tracks("x", transport=httpx.MockTransport(explode))


async def test_the_audio_handle_is_never_returned() -> None:
    found = await load_tracks(
        "zanaris", transport=answering({"loadType": "search", "data": [TRACK]})
    )

    assert "encoded" not in found[0]


async def test_searching_requires_a_login(anon_client: AsyncClient) -> None:
    assert (await anon_client.get("/music/search?q=zanaris")).status_code == 401


async def test_an_unknown_source_is_refused(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/music/search?q=x&source=vinyl")

    assert response.status_code == 422
    assert "vinyl" in response.json()["detail"]


async def test_an_empty_query_is_refused(auth_client: AsyncClient) -> None:
    assert (await auth_client.get("/music/search?q=")).status_code == 422


async def test_search_is_unavailable_when_lavalink_is_not_configured(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No node means no search, rather than a control that fails when pressed.
    monkeypatch.setattr(lavalink, "LAVALINK_URI", "")

    response = await auth_client.get("/music/search?q=zanaris")
    assert response.status_code == 503


SPOTIFY_PLAYLIST = "https://open.spotify.com/playlist/2jx0cXbScZnunVPmOlWRBE"


def error_body(*causes: str) -> dict[str, Any]:
    """A load failure shaped like Lavalink's, with the reasons it buries."""
    trace = (
        "com.sedmelluq.discord.lavaplayer.tools.FriendlyException:"
        " Something went wrong while looking up the track.\n"
    )
    for cause in causes:
        trace += f"Caused by: {cause}\n\tat some.Frame(Frame.java:1)\n"
    return {
        "loadType": "error",
        "data": {
            "message": "Something went wrong while looking up the track.",
            "severity": "fault",
            "causeStackTrace": trace,
        },
    }


async def test_a_spotify_generated_playlist_says_which_links_those_are() -> None:
    body = error_body(
        "com.sedmelluq.discord.lavaplayer.tools.FriendlyException: Spotify"
        " generated playlists are no longer accessible via anonymous tokens."
    )

    with pytest.raises(SearchError) as refused:
        await load_tracks(
            "https://open.spotify.com/playlist/37i9dQZF1DW", transport=answering(body)
        )

    message = str(refused.value)
    assert "anonymous tokens" not in message
    assert "37i9dQZ" in message
    assert "YouTube" in message


async def test_a_spotify_playlist_refusal_explains_the_account_requirement() -> None:
    # Spotify answers 401 "Valid user authentication required" here; all that
    # reaches us is a bare status buried in the trace.
    body = error_body(
        "com.sedmelluq.discord.lavaplayer.tools.FriendlyException: Server"
        " responded with an error.",
        "java.lang.IllegalStateException: Response code from channel info is 401",
    )

    with pytest.raises(SearchError) as refused:
        await load_tracks(SPOTIFY_PLAYLIST, transport=answering(body))

    message = str(refused.value)
    assert "signed-in Spotify account" in message
    assert "track links still work" in message
    assert "401" not in message


async def test_a_spotify_album_refusal_says_the_same_thing() -> None:
    # Albums and artist pages answer 403 rather than 401, same cause.
    body = error_body(
        "java.lang.IllegalStateException: Response code from channel info is 403"
    )

    with pytest.raises(SearchError, match="signed-in Spotify account"):
        await load_tracks(
            "https://open.spotify.com/album/abc", transport=answering(body)
        )


async def test_the_same_status_from_elsewhere_is_not_blamed_on_spotify() -> None:
    body = error_body(
        "java.lang.IllegalStateException: Response code from channel info is 401"
    )

    with pytest.raises(SearchError) as refused:
        await load_tracks(
            "https://www.youtube.com/playlist?list=abc", transport=answering(body)
        )

    assert "Spotify" not in str(refused.value)


async def test_the_deepest_cause_beats_lavaplayers_generic_one() -> None:
    body = error_body(
        "com.sedmelluq.discord.lavaplayer.tools.FriendlyException: Server"
        " responded with an error.",
        "java.lang.IllegalStateException: Response code from channel info is 404",
    )

    with pytest.raises(SearchError, match="channel info is 404"):
        await load_tracks("https://example.invalid/x", transport=answering(body))


async def test_an_error_without_a_deeper_cause_uses_what_it_was_given() -> None:
    body = {"loadType": "error", "data": {"message": "no such video"}}

    with pytest.raises(SearchError, match="no such video"):
        await load_tracks("x", transport=answering(body))
