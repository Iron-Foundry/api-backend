"""Endpoint-level tests for the music playlist routes.

Behaviour that depends on real rows - visibility, ownership, ordering - is
covered against Postgres in `integration/test_music_integration.py`. What is
asserted here is the surface: which routes exist, which require a login, and
which bodies are refused before they reach the database.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient

from app.routers.music._schemas import (
    NAME_MAX,
    TRACKS_MAX,
    PlaylistDetailOut,
    TrackIn,
    TrackOut,
)

_FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"

TRACK: dict[str, Any] = {
    "source": "spotify",
    "identifier": "abc123",
    "title": "Zanaris Nocturne",
    "author": "Barbarian Assault",
    "duration_ms": 180_000,
    "isrc": "USABC1234567",
}

WRITE_ROUTES = [
    ("post", "/music/playlists", {"name": "x", "tracks": []}),
    ("patch", "/music/playlists/1", {"name": "x"}),
    ("delete", "/music/playlists/1", None),
    ("put", "/music/playlists/1/tracks", {"tracks": []}),
    ("post", "/music/playlists/1/tracks", {"tracks": [TRACK]}),
]


@pytest.mark.parametrize(("method", "path", "body"), WRITE_ROUTES)
async def test_writes_require_a_login(
    anon_client: AsyncClient, method: str, path: str, body: dict[str, Any] | None
) -> None:
    response = await getattr(anon_client, method)(
        path, **({"json": body} if body is not None else {})
    )
    assert response.status_code == 401


async def test_listing_is_open_to_anonymous_callers(
    anon_client: AsyncClient, mock_session: MagicMock
) -> None:
    mock_session.execute.return_value.scalars.return_value.all.return_value = []
    response = await anon_client.get("/music/playlists")

    assert response.status_code == 200
    assert response.json() == []


async def test_scope_must_be_one_of_the_three(auth_client: AsyncClient) -> None:
    assert (
        await auth_client.get("/music/playlists", params={"scope": "everything"})
    ).status_code == 422


@pytest.mark.parametrize("scope", ["mine", "public", "all"])
async def test_each_scope_is_accepted(
    auth_client: AsyncClient, mock_session: MagicMock, scope: str
) -> None:
    mock_session.execute.return_value.scalars.return_value.all.return_value = []
    response = await auth_client.get("/music/playlists", params={"scope": scope})

    assert response.status_code == 200


async def test_a_missing_playlist_is_reported_as_missing(
    auth_client: AsyncClient, mock_session: MagicMock
) -> None:
    mock_session.execute.return_value.scalar_one_or_none.return_value = None
    assert (await auth_client.get("/music/playlists/1")).status_code == 404


async def test_a_playlist_needs_a_name(auth_client: AsyncClient) -> None:
    response = await auth_client.post(
        "/music/playlists", json={"name": "", "tracks": []}
    )
    assert response.status_code == 422


async def test_a_playlist_name_has_a_ceiling(auth_client: AsyncClient) -> None:
    response = await auth_client.post(
        "/music/playlists", json={"name": "x" * (NAME_MAX + 1), "tracks": []}
    )
    assert response.status_code == 422


async def test_a_playlist_cannot_be_created_unbounded(
    auth_client: AsyncClient,
) -> None:
    # Without a cap one request could write half a million rows.
    response = await auth_client.post(
        "/music/playlists",
        json={"name": "huge", "tracks": [TRACK] * (TRACKS_MAX + 1)},
    )
    assert response.status_code == 422


async def test_a_track_needs_its_identifying_fields(auth_client: AsyncClient) -> None:
    response = await auth_client.post(
        "/music/playlists",
        json={"name": "x", "tracks": [{"title": "Only a title"}]},
    )
    assert response.status_code == 422


async def test_a_negative_duration_is_refused(auth_client: AsyncClient) -> None:
    response = await auth_client.post(
        "/music/playlists",
        json={"name": "x", "tracks": [{**TRACK, "duration_ms": -1}]},
    )
    assert response.status_code == 422


async def test_the_bot_surface_needs_the_service_key(
    anon_client: AsyncClient,
) -> None:
    # verify_metrics_key is overridden in the fixtures, so this asserts the
    # route exists and is mounted under the service-key dependency rather than
    # the user JWT one.
    response = await anon_client.get("/music/bot/1234/playlists")
    assert response.status_code != 401


@pytest.mark.skipif(
    not _FIXTURES.exists(),
    reason="root fixtures/ not present (submodule-only checkout)",
)
def test_the_playlist_payload_matches_the_shared_contract() -> None:
    # discord-utils parses this payload with its own models, so a renamed or
    # dropped field here breaks a consumer no test in this repo would notice.
    body = json.loads((_FIXTURES / "music_playlist.json").read_text())

    assert set(PlaylistDetailOut.model_fields) == set(body), (
        "PlaylistDetailOut drifted from fixtures/music_playlist.json"
    )
    assert set(TrackOut.model_fields) == set(body["tracks"][0])


def test_the_isrc_is_optional() -> None:
    # YouTube and SoundCloud results carry no ISRC, and they are still saveable.
    # Whether such a track round-trips is asserted against Postgres instead.
    assert TrackIn(**{**TRACK, "isrc": None}).isrc is None
