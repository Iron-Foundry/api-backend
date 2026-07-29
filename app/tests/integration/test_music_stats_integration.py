"""The Stage 8 exit criterion: real counter rows after a synthetic event batch.

Everything here is real - a Valkey stream with a consumer group, Postgres with
the migration applied, and the upserts running against it. Mocking either would
prove nothing: what is under test is that the arithmetic Postgres does on
conflict is the arithmetic intended, and that a redelivered message does not
change the answer.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from app.services.music_stats import MusicStatsService
from app.services.music_stream import CONSUMER, GROUP, STREAM

pytestmark = pytest.mark.integration

GUILD = 1234


def played(**overrides: str) -> dict[str, str]:
    """One track_played event, shaped exactly as discord-utils writes it."""
    event = {
        "event": "track_played",
        "guild_id": str(GUILD),
        "isrc": "USABC1234567",
        "title": "Zanaris Nocturne",
        "author": "Barbarian Assault",
        "identifier": "abc123",
        "requested_source": "spotify",
        "played_source": "youtube",
        "length_ms": "180000",
        "listened_ms": "180000",
    }
    event.update(overrides)
    return event


@pytest.fixture
async def consumer(app: FastAPI, _truncate: None):
    """A stats consumer over a stream and group that start out empty.

    The lifespan already started one, and it would race this test for the same
    messages, so it is stopped for the duration: the point here is to drive one
    poll and read what it wrote, not to watch a background loop.
    """
    running = app.state.service_registry.get("music_stats")
    if running is not None and running.is_running:
        await running.stop()

    valkey = app.state.valkey
    await valkey.delete(STREAM)
    # The request client is injected rather than letting the service open its
    # own: every read here is non-blocking, and sharing one connection keeps the
    # seeded events and the consumer on the same server without a second pool.
    service = MusicStatsService("", app.state.session_factory, valkey=valkey)
    await service.ensure_group()
    yield service
    await valkey.delete(STREAM)


def _decoded(value: Any) -> Any:
    """JSONB read through a bare text() query comes back undecoded."""
    return json.loads(value) if isinstance(value, str) else value


async def counters(engine: AsyncEngine) -> list[dict[str, Any]]:
    async with engine.connect() as conn:
        rows = await conn.execute(sa.text("SELECT * FROM music_counters"))
        return [{**row, "sources": _decoded(row["sources"])} for row in rows.mappings()]


async def track_plays(engine: AsyncEngine) -> list[Any]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            sa.text("SELECT * FROM music_track_plays ORDER BY play_count DESC")
        )
        return list(rows.mappings())


async def test_a_batch_of_events_becomes_real_counter_rows(
    app: FastAPI, consumer: MusicStatsService, seed_engine: AsyncEngine
) -> None:
    for _ in range(3):
        await app.state.valkey.xadd(STREAM, played())
    await app.state.valkey.xadd(STREAM, played(event="track_skipped", listened_ms="20"))
    await app.state.valkey.xadd(
        STREAM, {"event": "session_started", "guild_id": "1234"}
    )

    assert await consumer.consume_once() == 5

    rows = await counters(seed_engine)
    assert len(rows) == 1
    assert rows[0]["guild_id"] == GUILD
    assert rows[0]["tracks_played"] == 3
    assert rows[0]["skips"] == 1
    assert rows[0]["sessions"] == 1
    assert rows[0]["ms_listened"] == 540_020


async def test_the_source_split_counts_where_the_audio_came_from(
    app: FastAPI, consumer: MusicStatsService, seed_engine: AsyncEngine
) -> None:
    # A Spotify request that streamed from YouTube counts as YouTube. That is
    # the whole reason played_source is carried separately.
    await app.state.valkey.xadd(STREAM, played())
    await app.state.valkey.xadd(STREAM, played())
    await app.state.valkey.xadd(STREAM, played(played_source="soundcloud"))
    await consumer.consume_once()

    rows = await counters(seed_engine)
    assert rows[0]["sources"] == {"youtube": 2, "soundcloud": 1}


async def test_two_guilds_keep_their_own_rows(
    app: FastAPI, consumer: MusicStatsService, seed_engine: AsyncEngine
) -> None:
    await app.state.valkey.xadd(STREAM, played())
    await app.state.valkey.xadd(STREAM, played(guild_id="9999"))
    await consumer.consume_once()

    rows = await counters(seed_engine)
    assert {row["guild_id"] for row in rows} == {GUILD, 9999}


async def test_one_recording_accumulates_across_sources(
    app: FastAPI, consumer: MusicStatsService, seed_engine: AsyncEngine
) -> None:
    await app.state.valkey.xadd(STREAM, played())
    await app.state.valkey.xadd(
        STREAM, played(played_source="spotify", title="Zanaris Nocturne (Remaster)")
    )
    await app.state.valkey.xadd(STREAM, played(event="track_skipped"))
    await consumer.consume_once()

    rows = await track_plays(seed_engine)
    assert len(rows) == 1
    assert rows[0]["track_key"] == "isrc:USABC1234567"
    assert rows[0]["has_isrc"] is True
    assert rows[0]["play_count"] == 2
    assert rows[0]["skip_count"] == 1
    assert rows[0]["last_played_at"] is not None


async def test_a_track_without_an_isrc_still_gets_a_row(
    app: FastAPI, consumer: MusicStatsService, seed_engine: AsyncEngine
) -> None:
    await app.state.valkey.xadd(STREAM, played(isrc="", title="Homemade Shanty"))
    await consumer.consume_once()

    rows = await track_plays(seed_engine)
    assert rows[0]["has_isrc"] is False
    assert rows[0]["track_key"].startswith("md:")


async def test_a_replayed_message_does_not_double_the_totals(
    app: FastAPI, consumer: MusicStatsService, seed_engine: AsyncEngine
) -> None:
    # Delivery is at least once. Without the SET NX claim, one redelivery after
    # a crash would inflate a total nobody can audit back down.
    message_id = await app.state.valkey.xadd(STREAM, played())
    await consumer.consume_once()

    # Put it back into the group's pending list, exactly as a worker that died
    # between the commit and the acknowledgement would leave it.
    await app.state.valkey.xclaim(STREAM, GROUP, CONSUMER, 0, [message_id], force=True)
    await consumer.consume_once()

    rows = await counters(seed_engine)
    assert rows[0]["tracks_played"] == 1


async def test_a_counted_message_is_acknowledged(
    app: FastAPI, consumer: MusicStatsService
) -> None:
    await app.state.valkey.xadd(STREAM, played())
    await consumer.consume_once()

    pending = await app.state.valkey.xpending(STREAM, GROUP)
    assert pending["pending"] == 0


async def test_an_unknown_event_is_ignored_rather_than_stalling_the_group(
    app: FastAPI, consumer: MusicStatsService, seed_engine: AsyncEngine
) -> None:
    await app.state.valkey.xadd(STREAM, {"event": "who_knows", "guild_id": "1234"})
    await app.state.valkey.xadd(STREAM, played())

    assert await consumer.consume_once() == 2
    rows = await counters(seed_engine)
    assert rows[0]["tracks_played"] == 1


async def test_the_totals_read_back_through_the_api(
    app: FastAPI,
    consumer: MusicStatsService,
    client: AsyncClient,
) -> None:
    await app.state.valkey.xadd(STREAM, played())
    await app.state.valkey.xadd(
        STREAM, played(event="track_skipped", listened_ms="500")
    )
    await consumer.consume_once()

    body = (await client.get("/music/stats")).json()

    assert body["tracks_played"] == 1
    assert body["skips"] == 1
    assert body["ms_listened"] == 180_500
    assert body["sources"] == {"youtube": 2}
    assert len(body["days"]) == 1


async def test_top_tracks_read_back_through_the_api(
    app: FastAPI,
    consumer: MusicStatsService,
    client: AsyncClient,
) -> None:
    await app.state.valkey.xadd(STREAM, played())
    await app.state.valkey.xadd(STREAM, played(isrc="USXYZ7654321", title="Sea Shanty"))
    await app.state.valkey.xadd(STREAM, played(isrc="USXYZ7654321", title="Sea Shanty"))
    await consumer.consume_once()

    body = (await client.get("/music/stats/top-tracks")).json()

    assert [row["title"] for row in body] == ["Sea Shanty", "Zanaris Nocturne"]
    assert body[0]["play_count"] == 2
