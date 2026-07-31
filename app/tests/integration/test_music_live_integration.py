"""The live music surface against a real Valkey.

The mocked suite proves the routes exist and refuse what they should. What only
a real server can show is that the keys discord-utils writes are the keys this
reads, that a command actually lands on the pubsub channel a subscriber is
listening to, and that a state notice reaches a watching socket.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.routers.music._live_keys import (
    ACTIVITY,
    COMMANDS_CHANNEL,
    HISTORY,
    QUEUE,
    SESSION,
    VOICE,
)
from app.services.music_live import MusicStateService, music_hub
from app.tests.conftest import TEST_USER

_FIXTURES = Path(__file__).resolve().parents[4] / "fixtures"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _FIXTURES.exists(),
        reason="root fixtures/ not present (submodule-only checkout)",
    ),
]

CHANNEL_ID = 555000111
BASE = f"/music/sessions/{CHANNEL_ID}"
ACTOR_ID = int(TEST_USER["sub"])
DELIVERY_TIMEOUT_SECONDS = 5


def bridge_fixture() -> dict[str, Any]:
    return json.loads((_FIXTURES / "music_bridge.json").read_text())


def queued_track(title: str, length_ms: int) -> str:
    stored = json.loads(bridge_fixture()["session_hash"]["track"])
    return json.dumps({**stored, "title": title, "length_ms": length_ms})


class FakeSocket:
    """Stands in for a watching browser."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_text(self, message: str) -> None:
        self.sent.append(json.loads(message))


@pytest.fixture
async def seeded(app: FastAPI):
    """One live session in Valkey, exactly as discord-utils would leave it."""
    valkey = app.state.valkey
    await valkey.hset(
        SESSION.format(voice_channel_id=CHANNEL_ID),
        mapping=bridge_fixture()["session_hash"],
    )
    await valkey.rpush(
        QUEUE.format(voice_channel_id=CHANNEL_ID),
        queued_track("Sea Shanty 2", 120_000),
        queued_track("Harmony", 90_000),
    )
    await valkey.sadd(VOICE.format(voice_channel_id=CHANNEL_ID), str(ACTOR_ID))
    await valkey.rpush(
        ACTIVITY.format(voice_channel_id=CHANNEL_ID),
        json.dumps(
            {
                "at": "2026-07-28T10:00:00Z",
                "actor_id": ACTOR_ID,
                "action": "queued",
                "detail": "Sea Shanty 2",
            }
        ),
    )
    await valkey.rpush(
        HISTORY.format(voice_channel_id=CHANNEL_ID),
        bridge_fixture()["history_entry"],
    )
    yield valkey
    await valkey.delete(
        SESSION.format(voice_channel_id=CHANNEL_ID),
        QUEUE.format(voice_channel_id=CHANNEL_ID),
        VOICE.format(voice_channel_id=CHANNEL_ID),
        ACTIVITY.format(voice_channel_id=CHANNEL_ID),
        HISTORY.format(voice_channel_id=CHANNEL_ID),
    )


async def test_a_seeded_session_reads_back_through_the_api(
    client: AsyncClient, seeded: Any
) -> None:
    body = (await client.get(BASE)).json()

    assert body["channel_name"] == "Music Lounge"
    assert body["current"]["title"] == "Zanaris Nocturne"
    assert body["queue_length"] == 2
    assert body["remaining_ms"] == 210_000
    assert body["listener_count"] == 1


async def test_history_reads_back_off_the_key_the_bot_writes(
    client: AsyncClient, seeded: Any
) -> None:
    # The key name is duplicated on both sides rather than shared as a package,
    # so this is the only place the two spellings actually meet.
    body = (await client.get(f"{BASE}/history")).json()

    assert len(body) == 1
    assert body[0]["track"]["title"] == "Zanaris Nocturne"
    assert body[0]["event"] == "skipped"


async def test_the_session_list_finds_it_by_scanning(
    client: AsyncClient, seeded: Any
) -> None:
    # The website has no way to know which channels are live, so discovery is
    # a scan of the session keys rather than a registry that could drift.
    ids = [
        row["voice_channel_id"] for row in (await client.get("/music/sessions")).json()
    ]

    assert str(CHANNEL_ID) in ids


async def test_the_queue_comes_back_in_play_order(
    client: AsyncClient, seeded: Any
) -> None:
    titles = [row["title"] for row in (await client.get(f"{BASE}/queue")).json()]

    assert titles == ["Sea Shanty 2", "Harmony"]


async def test_the_activity_feed_reads_back(client: AsyncClient, seeded: Any) -> None:
    entries = (await client.get(f"{BASE}/activity")).json()

    assert entries[0]["action"] == "queued"
    assert entries[0]["actor_id"] == str(ACTOR_ID)


async def test_being_in_the_channel_grants_control(
    client: AsyncClient, seeded: Any
) -> None:
    assert (await client.get(f"{BASE}/control")).json() == {"may_control": True}


async def test_leaving_the_channel_takes_control_away(
    client: AsyncClient, seeded: Any
) -> None:
    await seeded.srem(VOICE.format(voice_channel_id=CHANNEL_ID), str(ACTOR_ID))

    assert (await client.get(f"{BASE}/control")).json() == {"may_control": False}
    assert (
        await client.post(f"{BASE}/commands", json={"action": "skip"})
    ).status_code == 403


async def test_a_command_lands_on_the_channel_the_bridge_listens_to(
    client: AsyncClient, seeded: Any
) -> None:
    async with seeded.pubsub() as ps:
        await ps.subscribe(COMMANDS_CHANNEL)
        # The subscribe confirmation arrives first and is not the command.
        await ps.get_message(timeout=5)

        response = await client.post(
            f"{BASE}/commands", json={"action": "seek", "position_ms": 90_000}
        )
        assert response.status_code == 200

        delivered = await _next_message(ps)

    assert json.loads(delivered) == bridge_fixture()["command"]


async def test_a_state_notice_reaches_a_watching_socket(
    app: FastAPI, seeded: Any
) -> None:
    service = MusicStateService("unused", app.state.valkey)
    socket = FakeSocket()
    socket_id = music_hub.connect(socket)  # type: ignore[arg-type]
    try:
        await service.handle(json.dumps(bridge_fixture()["state_notice"]))
    finally:
        music_hub.disconnect(socket_id)

    assert socket.sent[0]["type"] == "session"
    assert socket.sent[0]["session"]["current"]["title"] == "Zanaris Nocturne"


async def test_a_closed_notice_tells_the_page_the_session_ended(
    app: FastAPI, seeded: Any
) -> None:
    service = MusicStateService("unused", app.state.valkey)
    socket = FakeSocket()
    socket_id = music_hub.connect(socket)  # type: ignore[arg-type]
    try:
        await service.handle(
            json.dumps({"voice_channel_id": CHANNEL_ID, "event": "closed"})
        )
    finally:
        music_hub.disconnect(socket_id)

    assert socket.sent == [{"type": "closed", "voice_channel_id": CHANNEL_ID}]


async def test_a_notice_for_an_expired_session_reads_as_closed(app: FastAPI) -> None:
    # The keys carry a TTL, so they can disappear between the notice being
    # published and this read. That is an ended session, not an error.
    service = MusicStateService("unused", app.state.valkey)
    socket = FakeSocket()
    socket_id = music_hub.connect(socket)  # type: ignore[arg-type]
    try:
        await service.handle(
            json.dumps({"voice_channel_id": 999000999, "event": "changed"})
        )
    finally:
        music_hub.disconnect(socket_id)

    assert socket.sent == [{"type": "closed", "voice_channel_id": 999000999}]


async def _next_message(pubsub: Any) -> str:
    """The next real message, skipping the subscribe confirmations."""
    async with asyncio.timeout(DELIVERY_TIMEOUT_SECONDS):
        while True:
            message = await pubsub.get_message(timeout=1)
            if message and message["type"] == "message":
                return message["data"]
