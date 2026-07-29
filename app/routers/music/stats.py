"""What the clan has listened to.

Read straight off the two counter tables. There is no per-user query here and
no way to write one: the rows carry a guild and a track, never a member, which
is the design's one-way privacy decision rather than a filter applied on the
way out.

Any signed-in member may read this, the same as the live session surface.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.music import MusicCounter, MusicTrackPlay
from app.dependencies import get_current_user, get_session

from ._stats_schemas import ClanStatsOut, DayOut, TopTrackOut

router = APIRouter(prefix="/stats")

SessionDep = Annotated[AsyncSession, Depends(get_session)]
UserDep = Annotated[dict[str, Any], Depends(get_current_user)]

DEFAULT_DAYS = 30
MAX_DAYS = 365
DEFAULT_TOP = 25
MAX_TOP = 100


@router.get("")
async def get_clan_stats(
    session: SessionDep,
    current_user: UserDep,
    days: Annotated[int, Query(ge=1, le=MAX_DAYS)] = DEFAULT_DAYS,
) -> ClanStatsOut:
    """Clan totals over a window, plus the per-day series behind them."""
    since = datetime.now(UTC).date() - timedelta(days=days - 1)
    rows = (
        (
            await session.execute(
                select(MusicCounter)
                .where(MusicCounter.day >= since)
                .order_by(MusicCounter.day)
            )
        )
        .scalars()
        .all()
    )
    return _totals(list(rows), days)


@router.get("/top-tracks")
async def get_top_tracks(
    session: SessionDep,
    current_user: UserDep,
    limit: Annotated[int, Query(ge=1, le=MAX_TOP)] = DEFAULT_TOP,
) -> list[TopTrackOut]:
    """The most-played recordings, keyed on identity rather than on source."""
    rows = (
        (
            await session.execute(
                select(MusicTrackPlay)
                .order_by(MusicTrackPlay.play_count.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [
        TopTrackOut(
            track_key=row.track_key,
            has_isrc=row.has_isrc,
            title=row.title,
            author=row.author,
            play_count=row.play_count,
            skip_count=row.skip_count,
            last_played_at=row.last_played_at,
        )
        for row in rows
    ]


def _totals(rows: list[MusicCounter], days: int) -> ClanStatsOut:
    """Fold the per-guild, per-day rows into one clan-wide answer.

    Summed in Python rather than in SQL because the window is at most a year of
    rows per guild and the source split is JSONB: merging it here keeps one
    readable pass instead of an aggregate plus a second query for the split.
    """
    sources: Counter[str] = Counter()
    per_day: dict[Any, DayOut] = {}
    for row in rows:
        sources.update(row.sources or {})
        day = per_day.setdefault(row.day, DayOut(day=row.day))
        day.ms_listened += row.ms_listened
        day.tracks_played += row.tracks_played
        day.skips += row.skips
        day.sessions += row.sessions

    series = sorted(per_day.values(), key=lambda entry: entry.day)
    return ClanStatsOut(
        days_requested=days,
        ms_listened=sum(day.ms_listened for day in series),
        tracks_played=sum(day.tracks_played for day in series),
        skips=sum(day.skips for day in series),
        sessions=sum(day.sessions for day in series),
        sources=dict(sources.most_common()),
        days=series,
    )
