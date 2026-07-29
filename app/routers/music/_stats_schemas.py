"""Response bodies for the clan listening stats.

Nothing here names a person. The counters behind them are per guild and per
track, so there is no per-user shape to leak even by accident - and that is a
property of the schema, not only of the query that fills it.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class DayOut(BaseModel):
    """One day's totals, for the shape of a graph."""

    day: date
    ms_listened: int = 0
    tracks_played: int = 0
    skips: int = 0
    sessions: int = 0


class ClanStatsOut(BaseModel):
    """What the clan listened to over a window, and how it splits by source.

    `sources` counts where the audio actually came from rather than where it
    was asked for, which is the only reason `played_source` is tracked at all -
    a Spotify request that streamed from YouTube counts as YouTube.
    """

    days_requested: int
    ms_listened: int = 0
    tracks_played: int = 0
    skips: int = 0
    sessions: int = 0
    sources: dict[str, int] = {}
    days: list[DayOut] = []


class TopTrackOut(BaseModel):
    """One recording and how often it has been played.

    `has_isrc` is exposed because it says how much to trust the row: an ISRC is
    a real identity, while the fallback key is a digest of the metadata and can
    split one recording that two sources title differently.
    """

    track_key: str
    has_isrc: bool
    title: str
    author: str
    play_count: int
    skip_count: int
    last_played_at: datetime | None = None
