"""The clan stats surface and the consumer that fills it.

Postgres is mocked here; that the rows really land is asserted against live
containers in `integration/test_music_stats_integration.py`. What is asserted
here is the arithmetic that has no database in it - track identity, the fold
from per-day rows into one answer - and the consumer's delivery semantics,
which are Valkey behaviour rather than SQL.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import date
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.db.models.music import MusicCounter
from app.routers.music._stats_schemas import ClanStatsOut, TopTrackOut
from app.routers.music.stats import MAX_DAYS, MAX_TOP, _totals
from app.services.music_identity import track_key
from app.services.music_stats import MusicStatsService
from app.services.music_stream import GROUP, STREAM

PLAYED = {
    b"event": b"track_played",
    b"guild_id": b"1234",
    b"isrc": b"USABC1234567",
    b"title": b"Zanaris Nocturne",
    b"author": b"Barbarian Assault",
    b"identifier": b"abc123",
    b"requested_source": b"spotify",
    b"played_source": b"youtube",
    b"length_ms": b"180000",
    b"listened_ms": b"180000",
}


def counter(day: date, **kwargs: Any) -> MusicCounter:
    values: dict[str, Any] = {
        "guild_id": 1234,
        "day": day,
        "ms_listened": 0,
        "tracks_played": 0,
        "skips": 0,
        "sessions": 0,
        "sources": {},
    }
    values.update(kwargs)
    return MusicCounter(**values)


def fake_valkey(messages: list[tuple[bytes, dict[bytes, bytes]]]) -> AsyncMock:
    """A Valkey that has `messages` waiting as new, and nothing pending."""
    valkey = AsyncMock()
    valkey.xreadgroup.side_effect = [[], [(STREAM.encode(), messages)]]
    valkey.set.return_value = True
    return valkey


def fake_factory(session: AsyncMock) -> Any:
    @asynccontextmanager
    async def factory() -> AsyncGenerator[AsyncMock]:
        yield session

    return factory


def test_a_recording_is_identified_by_its_isrc_when_it_has_one() -> None:
    key, has_isrc = track_key("usabc1234567", "Zanaris", "Barbarian", 180_000)

    assert key == "isrc:USABC1234567"
    assert has_isrc is True


def test_the_same_recording_from_two_sources_shares_one_key() -> None:
    # Keying on the source identifier would list one song twice in "top tracks".
    spotify, _ = track_key("USABC1234567", "Zanaris", "Barbarian", 180_000)
    youtube, _ = track_key("USABC1234567", "Zanaris (Official)", "Barbarian", 180_100)

    assert spotify == youtube


def test_a_track_without_an_isrc_falls_back_to_its_metadata() -> None:
    key, has_isrc = track_key("", "Zanaris", "Barbarian", 180_000)
    same, _ = track_key("", "  zanaris  ", "BARBARIAN", 180_400)

    assert has_isrc is False
    assert key == same
    assert key.startswith("md:")


def test_a_different_recording_gets_a_different_key() -> None:
    one, _ = track_key("", "Zanaris", "Barbarian", 180_000)
    other, _ = track_key("", "Lumbridge", "Barbarian", 180_000)

    assert one != other


def test_the_totals_are_the_sum_of_the_days_behind_them() -> None:
    rows = [
        counter(date(2026, 7, 1), ms_listened=1000, tracks_played=2, skips=1),
        counter(date(2026, 7, 2), ms_listened=500, tracks_played=1, sessions=1),
    ]

    totals = _totals(rows, 30)

    assert totals.ms_listened == 1500
    assert totals.tracks_played == 3
    assert totals.skips == 1
    assert totals.sessions == 1
    assert [day.day for day in totals.days] == [date(2026, 7, 1), date(2026, 7, 2)]


def test_two_guilds_on_one_day_fold_into_one_clan_day() -> None:
    rows = [
        counter(date(2026, 7, 1), guild_id=1, tracks_played=2),
        counter(date(2026, 7, 1), guild_id=2, tracks_played=3),
    ]

    totals = _totals(rows, 30)

    assert len(totals.days) == 1
    assert totals.days[0].tracks_played == 5


def test_the_source_split_counts_where_the_audio_came_from() -> None:
    rows = [
        counter(date(2026, 7, 1), sources={"youtube": 3, "soundcloud": 1}),
        counter(date(2026, 7, 2), sources={"youtube": 2}),
    ]

    totals = _totals(rows, 30)

    assert totals.sources == {"youtube": 5, "soundcloud": 1}


def test_an_empty_window_is_zeroes_rather_than_an_error() -> None:
    totals = _totals([], 7)

    assert totals.days_requested == 7
    assert totals.ms_listened == 0
    assert totals.days == []


async def test_reading_stats_requires_a_login(anon_client: AsyncClient) -> None:
    assert (await anon_client.get("/music/stats")).status_code == 401
    assert (await anon_client.get("/music/stats/top-tracks")).status_code == 401


@pytest.mark.parametrize(
    "path",
    [f"/music/stats?days={MAX_DAYS + 1}", "/music/stats?days=0"],
)
async def test_an_impossible_window_is_refused(
    auth_client: AsyncClient, path: str
) -> None:
    assert (await auth_client.get(path)).status_code == 422


async def test_asking_for_more_top_tracks_than_the_cap_is_refused(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.get(f"/music/stats/top-tracks?limit={MAX_TOP + 1}")

    assert response.status_code == 422


def test_no_stats_field_can_name_a_person() -> None:
    # The tables carry a guild and a track, never a member, so there is no
    # per-user filter to forget: the shape itself cannot describe one.
    named = set(ClanStatsOut.model_fields) | set(TopTrackOut.model_fields)

    assert not {field for field in named if "user" in field or "member" in field}
    assert "requester_id" not in named


async def test_a_new_message_is_counted_once_and_acknowledged() -> None:
    valkey = fake_valkey([(b"1-1", PLAYED)])
    session = AsyncMock()
    service = MusicStatsService("", fake_factory(session), valkey=valkey)

    assert await service.consume_once() == 1
    session.commit.assert_awaited_once()
    valkey.xack.assert_awaited_once_with(STREAM, GROUP, b"1-1")


async def test_a_redelivered_message_is_acknowledged_but_not_counted_again() -> None:
    # At-least-once delivery means a crash between the write and the ack replays
    # the message. Counting it twice would inflate a total nobody can audit.
    valkey = fake_valkey([(b"1-1", PLAYED)])
    valkey.set.return_value = None
    session = AsyncMock()
    service = MusicStatsService("", fake_factory(session), valkey=valkey)

    assert await service.consume_once() == 1
    session.execute.assert_not_awaited()
    valkey.xack.assert_awaited_once_with(STREAM, GROUP, b"1-1")


async def test_a_failed_write_releases_its_claim_for_the_retry() -> None:
    # Otherwise the claim outlives the transaction that failed and the event is
    # silently dropped when the message comes back.
    valkey = fake_valkey([(b"1-1", PLAYED)])
    session = AsyncMock()
    session.commit.side_effect = RuntimeError("no database")
    service = MusicStatsService("", fake_factory(session), valkey=valkey)

    with pytest.raises(RuntimeError):
        await service.consume_once()

    valkey.delete.assert_awaited_once_with("music:events:seen:1-1")
    valkey.xack.assert_not_awaited()


async def test_pending_messages_are_drained_before_new_ones() -> None:
    # A batch left behind by a worker that died mid-transaction must be retried
    # rather than sitting in the group forever.
    valkey = AsyncMock()
    valkey.xreadgroup.return_value = [(STREAM.encode(), [(b"1-1", PLAYED)])]
    valkey.set.return_value = True
    service = MusicStatsService("", fake_factory(AsyncMock()), valkey=valkey)

    await service.consume_once()

    assert valkey.xreadgroup.await_args_list[0].args[2] == {STREAM: "0"}


async def test_an_existing_consumer_group_is_not_an_error() -> None:
    valkey = AsyncMock()
    valkey.xgroup_create.side_effect = RuntimeError("BUSYGROUP already exists")

    await MusicStatsService("", None, valkey=valkey).ensure_group()


async def test_a_real_group_failure_is_still_raised() -> None:
    valkey = AsyncMock()
    valkey.xgroup_create.side_effect = RuntimeError("NOAUTH")

    with pytest.raises(RuntimeError):
        await MusicStatsService("", None, valkey=valkey).ensure_group()


def test_the_consumer_opens_its_own_connection_for_a_blocking_read() -> None:
    # A blocking XREADGROUP holds its socket for the whole block, and the shared
    # request client carries a socket timeout far shorter than that. Reusing it
    # made every poll time out and left the consumer in a retry loop that
    # counted nothing at all - visible only in the deployed stack's logs.
    service = MusicStatsService("redis://valkey:6379", None)

    kwargs = service.valkey.connection_pool.connection_kwargs
    assert kwargs["socket_timeout"] is None


def test_an_injected_client_is_used_as_given() -> None:
    injected = AsyncMock()

    assert MusicStatsService("redis://valkey:6379", None, valkey=injected).valkey is (
        injected
    )


async def test_the_consumer_does_not_start_without_a_database() -> None:
    service = MusicStatsService("", None, valkey=AsyncMock())

    await service.start()

    assert service.is_running is False


def test_the_event_names_match_what_the_bot_writes() -> None:
    # discord-utils/music/stats.py writes these strings; a rename on one side
    # would leave the counters permanently at zero rather than erroring.
    from app.services import music_counters

    assert music_counters.TRACK_PLAYED == "track_played"
    assert music_counters.TRACK_SKIPPED == "track_skipped"
    assert music_counters.SESSION_STARTED == "session_started"
    assert music_counters.SESSION_ENDED == "session_ended"
