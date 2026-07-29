"""Durable music state: playlists, and the anonymous play counters.

Sessions, queues and now-playing state live in Valkey and die with the session.
Only these four tables outlive one.

No user id is stored against playback. Counters are per guild and per track by
design, which closes the privacy question and makes retention a non-issue - but
it is also a one-way door: per-user history cannot be reconstructed later, not
even retroactively.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


def _now() -> datetime:
    return datetime.now(UTC)


class Playlist(Base):
    __tablename__ = "playlists"
    __table_args__ = (
        UniqueConstraint("owner_discord_id", "name", name="uq_playlist_owner_name"),
        Index("ix_playlists_public", "is_public"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_discord_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_public: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    # Timestamps are set in Python, not by the database. A SQL-expression
    # default is opaque to the ORM, which then expires the attribute after every
    # flush and re-reads it on next access - a lazy read that raises
    # MissingGreenlet under asyncio the moment a response is serialised.
    # The server defaults stay for rows written outside the ORM.
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=_now,
        onupdate=_now,
        server_default=func.now(),
    )

    tracks: Mapped[list[PlaylistTrack]] = relationship(
        "PlaylistTrack",
        back_populates="playlist",
        cascade="all, delete-orphan",
        order_by="PlaylistTrack.position",
    )


class PlaylistTrack(Base):
    """One track in a playlist.

    The ISRC is stored alongside the source identifier deliberately. A saved
    YouTube id dies when the video is taken down; with the ISRC the same
    recording can be found again on another source instead of vanishing from
    the playlist.
    """

    __tablename__ = "playlist_tracks"
    __table_args__ = (
        UniqueConstraint("playlist_id", "position", name="uq_playlist_track_position"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    playlist_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    isrc: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    identifier: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str] = mapped_column(Text, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    uri: Mapped[str | None] = mapped_column(Text)
    artwork: Mapped[str | None] = mapped_column(Text)

    playlist: Mapped[Playlist] = relationship("Playlist", back_populates="tracks")


class MusicCounter(Base):
    """Per-guild, per-day playback totals. Never per user."""

    __tablename__ = "music_counters"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    ms_listened: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    tracks_played: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    skips: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    sessions: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    sources: Mapped[dict[str, int]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )


class MusicTrackPlay(Base):
    """Per-track totals, keyed on identity rather than on source.

    `track_key` is the ISRC when the source gave one, and a normalised
    title/author/duration hash when it did not. Keying on the source identifier
    instead would split one song across Spotify and YouTube and make "top
    tracks" meaningless.
    """

    __tablename__ = "music_track_plays"
    __table_args__ = (Index("ix_music_track_plays_count", "play_count"),)

    track_key: Mapped[str] = mapped_column(Text, primary_key=True)
    has_isrc: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str] = mapped_column(Text, nullable=False)
    play_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    skip_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_played_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
