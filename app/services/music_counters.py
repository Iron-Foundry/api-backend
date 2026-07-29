"""Turning one music event into the anonymous counters.

Two tables, both additive: `music_counters` is per guild and per day, and
`music_track_plays` is per recording. Neither carries a user id - the design's
one-way privacy decision - which is what makes retention a non-question.

Postgres does the arithmetic inside the upsert rather than this process reading,
adding and writing back. Two workers consuming the same stream would otherwise
lose increments to each other, and the whole point of the stream is that more
than one may.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, cast

from sqlalchemy import Integer, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.music import MusicCounter, MusicTrackPlay
from app.services.music_identity import track_key

# The event names discord-utils writes onto the stream.
TRACK_PLAYED = "track_played"
TRACK_SKIPPED = "track_skipped"
SESSION_STARTED = "session_started"
SESSION_ENDED = "session_ended"

_TRACK_EVENTS = (TRACK_PLAYED, TRACK_SKIPPED)


async def apply_event(session: AsyncSession, fields: dict[str, str]) -> None:
    """Count one event. Anything unrecognised is ignored rather than raised on."""
    guild_id = int(fields.get("guild_id") or 0)
    event = fields.get("event", "")
    if not guild_id:
        return

    today = datetime.now(UTC).date()
    if event == SESSION_STARTED:
        await _bump_counter(session, guild_id, today, sessions=1)
        return
    if event not in _TRACK_EVENTS:
        return

    played = event == TRACK_PLAYED
    await _bump_counter(
        session,
        guild_id,
        today,
        ms_listened=int(fields.get("listened_ms") or 0),
        tracks_played=int(played),
        skips=int(not played),
        source=fields.get("played_source") or "",
    )
    await _bump_track(session, fields, played=played)


async def _bump_counter(
    session: AsyncSession,
    guild_id: int,
    day: date,
    *,
    ms_listened: int = 0,
    tracks_played: int = 0,
    skips: int = 0,
    sessions: int = 0,
    source: str = "",
) -> None:
    stmt = insert(MusicCounter).values(
        guild_id=guild_id,
        day=day,
        ms_listened=ms_listened,
        tracks_played=tracks_played,
        skips=skips,
        sessions=sessions,
        sources=_first_source(source),
    )
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[MusicCounter.guild_id, MusicCounter.day],
            set_={
                "ms_listened": MusicCounter.ms_listened + stmt.excluded.ms_listened,
                "tracks_played": (
                    MusicCounter.tracks_played + stmt.excluded.tracks_played
                ),
                "skips": MusicCounter.skips + stmt.excluded.skips,
                "sessions": MusicCounter.sessions + stmt.excluded.sessions,
                "sources": _merged_sources(source),
            },
        )
    )


async def _bump_track(
    session: AsyncSession, fields: dict[str, str], *, played: bool
) -> None:
    key, has_isrc = track_key(
        fields.get("isrc", ""),
        fields.get("title", ""),
        fields.get("author", ""),
        int(fields.get("length_ms") or 0),
    )
    stmt = insert(MusicTrackPlay).values(
        track_key=key,
        has_isrc=has_isrc,
        title=fields.get("title", ""),
        author=fields.get("author", ""),
        play_count=int(played),
        skip_count=int(not played),
        last_played_at=datetime.now(UTC),
    )
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[MusicTrackPlay.track_key],
            set_={
                "play_count": MusicTrackPlay.play_count + stmt.excluded.play_count,
                "skip_count": MusicTrackPlay.skip_count + stmt.excluded.skip_count,
                "last_played_at": stmt.excluded.last_played_at,
            },
        )
    )


def _first_source(source: str) -> dict[str, int]:
    return {source: 1} if source else {}


def _merged_sources(source: str) -> Any:
    """The stored split with one more play on `source`, counted by Postgres.

    Cast because the column is typed as a plain dict for the ORM; the JSONB
    subscript and `->>` belong to the dialect, not to that annotation.
    """
    stored = cast(Any, MusicCounter.sources)
    if not source:
        return stored
    current = func.coalesce(stored[source].astext.cast(Integer), 0)
    return stored.op("||")(func.jsonb_build_object(source, current + 1))
