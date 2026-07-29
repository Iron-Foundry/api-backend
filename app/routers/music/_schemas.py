"""Request and response bodies for the playlist routes.

The live session surface has its own bodies in `_live_schemas.py`.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

NAME_MAX = 60
TRACKS_MAX = 500


class TrackIn(BaseModel):
    """One track being saved into a playlist, or queued into a live session.

    `artwork` is carried rather than looked up again. A track only re-resolves
    its audio at play time, and the resolved result is a mirror on another
    source whose own cover art is not the one the user picked from, so a cover
    dropped here is gone for good.
    """

    source: str = Field(max_length=40)
    identifier: str = Field(max_length=256)
    title: str = Field(max_length=300)
    author: str = Field(max_length=300)
    duration_ms: int = Field(ge=0)
    isrc: str | None = Field(default=None, max_length=32)
    uri: str | None = Field(default=None, max_length=1000)
    artwork: str | None = Field(default=None, max_length=1000)


class TrackOut(TrackIn):
    position: int


class PlaylistOut(BaseModel):
    # A Discord id is a 64-bit snowflake and a JSON number is an IEEE double in
    # a browser, so anything above 2^53 arrives with its last digits rounded.
    # The owner id is what an "is this mine?" check compares, so it crosses as
    # a string; `id` is a database key and stays a number.
    model_config = ConfigDict(coerce_numbers_to_str=True)

    id: int
    owner_discord_id: str
    name: str
    is_public: bool
    track_count: int
    created_at: datetime
    updated_at: datetime


class PlaylistDetailOut(PlaylistOut):
    tracks: list[TrackOut]


class CreatePlaylistRequest(BaseModel):
    name: str = Field(min_length=1, max_length=NAME_MAX)
    is_public: bool = False
    tracks: list[TrackIn] = Field(default_factory=list, max_length=TRACKS_MAX)


class UpdatePlaylistRequest(BaseModel):
    """Only the fields present are changed."""

    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX)
    is_public: bool | None = None


class TracksRequest(BaseModel):
    tracks: list[TrackIn] = Field(max_length=TRACKS_MAX)
