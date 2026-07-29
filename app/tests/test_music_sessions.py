"""Endpoint-level tests for the live session surface.

What a real session looks like once it is in Valkey is covered against a live
container in `integration/test_music_live_integration.py`. Asserted here is the
surface: which routes need a login, what a missing session answers, and which
bodies never reach the publisher.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.routers.music._live_keys import COMMANDS_CHANNEL, STATE_CHANNEL
from app.routers.music._live_schemas import SessionOut

_FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"

CHANNEL_ID = 555000111
BASE = f"/music/sessions/{CHANNEL_ID}"

READ_ROUTES = [
    "/music/sessions",
    BASE,
    f"{BASE}/queue",
    f"{BASE}/activity",
    f"{BASE}/control",
]


def bridge_fixture() -> dict[str, Any]:
    return json.loads((_FIXTURES / "music_bridge.json").read_text())


def live_session(valkey: AsyncMock) -> None:
    """Make the mocked Valkey answer as though one session is playing."""
    hash_fields = bridge_fixture()["session_hash"]
    valkey.hgetall.return_value = {
        key.encode(): value.encode() for key, value in hash_fields.items()
    }
    valkey.lrange.return_value = []
    valkey.scard.return_value = 2
    valkey.sismember.return_value = True
    valkey.publish.return_value = 1


@pytest.mark.parametrize("path", READ_ROUTES)
async def test_reading_a_session_requires_a_login(
    anon_client: AsyncClient, path: str
) -> None:
    assert (await anon_client.get(path)).status_code == 401


async def test_commanding_a_session_requires_a_login(
    anon_client: AsyncClient,
) -> None:
    response = await anon_client.post(f"{BASE}/commands", json={"action": "skip"})
    assert response.status_code == 401


async def test_a_channel_with_no_session_is_not_found(
    auth_client: AsyncClient, mock_valkey: AsyncMock
) -> None:
    mock_valkey.hgetall.return_value = {}
    assert (await auth_client.get(BASE)).status_code == 404


async def test_a_session_reads_back_as_the_website_renders_it(
    auth_client: AsyncClient, mock_valkey: AsyncMock
) -> None:
    live_session(mock_valkey)
    body = (await auth_client.get(BASE)).json()

    assert body["voice_channel_id"] == str(CHANNEL_ID)
    assert body["channel_name"] == "Music Lounge"
    assert body["current"]["title"] == "Zanaris Nocturne"
    assert body["listener_count"] == 2
    assert body["paused"] is False


async def test_the_cover_and_the_requester_name_reach_the_browser(
    auth_client: AsyncClient, mock_valkey: AsyncMock
) -> None:
    # Both are stamped by discord-utils and cannot be recovered on this side:
    # the cover only exists once the audio has been resolved, and a snowflake
    # is not a name anywhere in this service.
    live_session(mock_valkey)
    track = (await auth_client.get(BASE)).json()["current"]

    assert track["artwork"] == "https://i.scdn.co/image/abc123"
    assert track["requester_name"] == "Saltis"


async def test_the_audio_handle_never_reaches_the_browser(
    auth_client: AsyncClient, mock_valkey: AsyncMock
) -> None:
    # The stored track carries the encoded Lavalink audio and its raw payload.
    # Echoing either would put a playable handle into a web page.
    live_session(mock_valkey)
    track = (await auth_client.get(BASE)).json()["current"]

    assert "encoded" not in track
    assert "payload" not in track


async def test_every_discord_id_crosses_as_a_string(
    auth_client: AsyncClient, mock_valkey: AsyncMock
) -> None:
    # A snowflake above 2^53 loses its last digits when a browser parses it as a
    # JSON number, and the rounded value addresses a channel nobody is in - so
    # every control silently reads as forbidden. These stay strings.
    live_session(mock_valkey)
    body = (await auth_client.get(BASE)).json()

    assert isinstance(body["voice_channel_id"], str)
    assert isinstance(body["guild_id"], str)
    assert isinstance(body["current"]["requester_id"], str)
    # Exact, not rounded: this is the digit that goes missing.
    assert body["current"]["requester_id"] == "111222333444555666"


async def test_a_real_snowflake_survives_the_round_trip(
    auth_client: AsyncClient, mock_valkey: AsyncMock
) -> None:
    snowflake = 1479967329084375071
    live_session(mock_valkey)

    body = (await auth_client.get(f"/music/sessions/{snowflake}")).json()

    assert body["voice_channel_id"] == str(snowflake)
    assert int(body["voice_channel_id"]) == snowflake


async def test_control_is_refused_to_someone_not_in_the_channel(
    auth_client: AsyncClient, mock_valkey: AsyncMock
) -> None:
    live_session(mock_valkey)
    mock_valkey.sismember.return_value = False

    response = await auth_client.post(f"{BASE}/commands", json={"action": "skip"})
    assert response.status_code == 403


async def test_a_command_for_a_dead_session_is_not_found(
    auth_client: AsyncClient, mock_valkey: AsyncMock
) -> None:
    mock_valkey.hgetall.return_value = {}
    response = await auth_client.post(f"{BASE}/commands", json={"action": "skip"})

    assert response.status_code == 404
    mock_valkey.publish.assert_not_called()


@pytest.mark.parametrize(
    ("action", "missing"),
    [("seek", "position_ms"), ("volume", "volume"), ("move", "index")],
)
async def test_an_action_without_its_argument_is_refused(
    auth_client: AsyncClient, mock_valkey: AsyncMock, action: str, missing: str
) -> None:
    live_session(mock_valkey)
    response = await auth_client.post(f"{BASE}/commands", json={"action": action})

    assert response.status_code == 422
    assert missing in response.json()["detail"]
    mock_valkey.publish.assert_not_called()


async def test_an_accepted_command_is_published_to_the_bridge(
    auth_client: AsyncClient, mock_valkey: AsyncMock
) -> None:
    live_session(mock_valkey)
    response = await auth_client.post(
        f"{BASE}/commands", json={"action": "seek", "position_ms": 90_000}
    )

    assert response.status_code == 200
    channel, payload = mock_valkey.publish.call_args.args
    assert channel == COMMANDS_CHANNEL
    assert json.loads(payload) == bridge_fixture()["command"]


async def test_resume_travels_as_pause_with_a_flag(
    auth_client: AsyncClient, mock_valkey: AsyncMock
) -> None:
    # discord-utils calls `player.pause(bool)`; two verbs exist only so a web
    # button can name what it does.
    live_session(mock_valkey)
    await auth_client.post(f"{BASE}/commands", json={"action": "resume"})

    published = json.loads(mock_valkey.publish.call_args.args[1])
    assert published["action"] == "pause"
    assert published["paused"] is False


async def test_added_tracks_travel_on_the_command(
    auth_client: AsyncClient, mock_valkey: AsyncMock
) -> None:
    # The bot must not re-search: the caller picked a specific result, and
    # running the query again could queue a different one.
    live_session(mock_valkey)
    track = {
        "source": "spotify",
        "identifier": "abc123",
        "title": "Zanaris Nocturne",
        "author": "Barbarian Assault",
        "duration_ms": 180_000,
        "isrc": "USABC1234567",
        "uri": "https://open.spotify.com/track/abc123",
        # Travels with the track. The bot has no way back to it: what it
        # resolves at play time is a mirror carrying a different cover.
        "artwork": "https://i.scdn.co/image/abc123",
    }

    response = await auth_client.post(
        f"{BASE}/commands", json={"action": "add", "tracks": [track]}
    )

    assert response.status_code == 200
    published = json.loads(mock_valkey.publish.call_args.args[1])
    assert published["action"] == "add"
    assert published["tracks"] == [track]


async def test_adding_nothing_is_refused(
    auth_client: AsyncClient, mock_valkey: AsyncMock
) -> None:
    live_session(mock_valkey)
    response = await auth_client.post(f"{BASE}/commands", json={"action": "add"})

    assert response.status_code == 422
    mock_valkey.publish.assert_not_called()


async def test_a_command_nobody_is_listening_for_says_so(
    auth_client: AsyncClient, mock_valkey: AsyncMock
) -> None:
    # The session hash outlives a crashed bot by its TTL, so this is a real
    # state rather than an impossible one.
    live_session(mock_valkey)
    mock_valkey.publish.return_value = 0

    response = await auth_client.post(f"{BASE}/commands", json={"action": "skip"})
    assert response.status_code == 503


def test_the_bridge_channels_match_the_shared_contract() -> None:
    channels = bridge_fixture()["channels"]

    assert channels["commands"] == COMMANDS_CHANNEL
    assert channels["state"] == STATE_CHANNEL


def test_every_hash_field_the_reader_needs_is_in_the_contract() -> None:
    # discord-utils writes this hash. A field renamed there and not here reads
    # back as a default, which no test in that repo would notice.
    written = set(bridge_fixture()["session_hash"])
    read = set(SessionOut.model_fields) - {
        "voice_channel_id",
        "current",
        "queue_length",
        "remaining_ms",
        "listener_count",
    }

    assert read <= written
