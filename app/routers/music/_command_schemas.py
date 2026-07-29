"""The bodies the website drives a session with.

Split from `_live_schemas.py`, which describes what is read. These describe what
is asked for, and they are the only shapes that leave api-backend on the
`music:commands` channel - so discord-utils pins them from its own side.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ._schemas import TRACKS_MAX, TrackIn


class CommandRequest(BaseModel):
    """A control the website is asking for.

    One body for every action rather than a route each: the fields a given
    action needs are validated by the router, and the whole thing travels to
    discord-utils as published JSON either way.
    """

    action: Literal[
        "pause",
        "resume",
        "skip",
        "stop",
        "shuffle",
        "seek",
        "volume",
        "loop",
        "add",
        "remove",
        "move",
        "jump",
        "load_playlist",
    ]
    # Carried on the command rather than searched again by the bot: the web
    # already resolved them, and re-searching could queue a different track than
    # the one the caller picked.
    tracks: list[TrackIn] | None = Field(default=None, max_length=TRACKS_MAX)
    index: int | None = Field(default=None, ge=0)
    destination: int | None = Field(default=None, ge=0)
    position_ms: int | None = Field(default=None, ge=0)
    volume: int | None = Field(default=None, ge=0, le=150)
    loop: Literal["off", "track", "queue"] | None = None
    # Sent explicitly rather than toggled by the bot, so two people pressing
    # at once cannot invert each other. Same reasoning as pause/resume.
    shuffle: bool | None = None
    playlist_id: int | None = Field(default=None, ge=1)


class CommandAccepted(BaseModel):
    """A command was published. Whether it changed anything arrives over the socket."""

    accepted: bool = True
    action: str
    delivered_to: int
