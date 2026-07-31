"""The session history endpoint.

The list itself is written by discord-utils; what is asserted here is that the
website is given the whole kept list rather than a page of it, that an entry
carries the metadata its two controls need, and that no playable audio handle
comes back with it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.routers.music.sessions import HISTORY_LIMIT

_FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"

pytestmark = pytest.mark.skipif(
    not _FIXTURES.exists(),
    reason="root fixtures/ not present (submodule-only checkout)",
)

CHANNEL_ID = 555000111
BASE = f"/music/sessions/{CHANNEL_ID}"


def bridge_fixture() -> dict[str, Any]:
    return json.loads((_FIXTURES / "music_bridge.json").read_text())


def live_session_with_history(valkey: AsyncMock, entries: int = 1) -> None:
    hash_fields = bridge_fixture()["session_hash"]
    valkey.hgetall.return_value = {
        key.encode(): value.encode() for key, value in hash_fields.items()
    }
    entry = bridge_fixture()["history_entry"].encode()
    # The session read runs first and reads the queue off the same client.
    valkey.lrange.side_effect = [[], [entry] * entries]
    valkey.scard.return_value = 2


async def test_reading_the_history_requires_a_login(anon_client: AsyncClient) -> None:
    assert (await anon_client.get(f"{BASE}/history")).status_code == 401


async def test_a_channel_with_no_session_has_no_history(
    auth_client: AsyncClient, mock_valkey: AsyncMock
) -> None:
    mock_valkey.hgetall.return_value = {}

    assert (await auth_client.get(f"{BASE}/history")).status_code == 404


async def test_an_entry_names_the_track_and_how_it_ended(
    auth_client: AsyncClient, mock_valkey: AsyncMock
) -> None:
    live_session_with_history(mock_valkey)

    body = (await auth_client.get(f"{BASE}/history")).json()

    assert len(body) == 1
    assert body[0]["event"] == "skipped"
    assert body[0]["track"]["title"] == "Zanaris Nocturne"
    assert body[0]["track"]["length_ms"] == 180_000


async def test_the_audio_handle_never_reaches_the_browser(
    auth_client: AsyncClient, mock_valkey: AsyncMock
) -> None:
    live_session_with_history(mock_valkey)

    track = (await auth_client.get(f"{BASE}/history")).json()[0]["track"]

    assert "encoded" not in track
    assert "payload" not in track


async def test_the_requester_crosses_as_a_string(
    auth_client: AsyncClient, mock_valkey: AsyncMock
) -> None:
    live_session_with_history(mock_valkey)

    track = (await auth_client.get(f"{BASE}/history")).json()[0]["track"]

    assert track["requester_id"] == "111222333444555666"


async def test_the_whole_kept_list_comes_back_by_default(
    auth_client: AsyncClient, mock_valkey: AsyncMock
) -> None:
    # The panel shows ten; the website is deliberately given everything the bot
    # still holds, which is the point of the two surfaces differing.
    live_session_with_history(mock_valkey, entries=HISTORY_LIMIT)

    body = (await auth_client.get(f"{BASE}/history")).json()

    assert HISTORY_LIMIT >= 100
    assert len(body) == HISTORY_LIMIT


async def test_asking_for_more_than_the_cap_is_refused(
    auth_client: AsyncClient, mock_valkey: AsyncMock
) -> None:
    live_session_with_history(mock_valkey)

    response = await auth_client.get(f"{BASE}/history?limit={HISTORY_LIMIT + 1}")

    assert response.status_code == 422


async def test_an_unreadable_entry_does_not_take_the_feed_down(
    auth_client: AsyncClient, mock_valkey: AsyncMock
) -> None:
    # One bad item written by an older bot must not blank the whole page.
    entry = bridge_fixture()["history_entry"].encode()
    mock_valkey.hgetall.return_value = {
        key.encode(): value.encode()
        for key, value in bridge_fixture()["session_hash"].items()
    }
    mock_valkey.lrange.side_effect = [[], [b"not json", entry]]
    mock_valkey.scard.return_value = 2

    body = (await auth_client.get(f"{BASE}/history")).json()

    assert len(body) == 1
