"""Response bodies for the live session surface.

Apart from the playlist schemas because these describe ephemeral Valkey state
rather than database rows, and because discord-utils pins them from its own
side: a field renamed here changes what the bot and the website agree on. What
the website asks for, rather than reads, is in `_command_schemas.py`.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from ._schemas import TrackIn

# Discord ids are 64-bit snowflakes and JSON numbers are IEEE doubles in a
# browser, so anything above 2^53 loses its last digits on the way in. Every id
# that reaches the web is therefore a string, and the numbers Valkey holds are
# coerced into one rather than being renamed at the source.
SNOWFLAKE_SAFE = ConfigDict(coerce_numbers_to_str=True)


class SessionTrack(BaseModel):
    """A track as discord-utils stores it, minus what the web cannot use.

    The stored row also carries the encoded Lavalink audio and its raw payload.
    Neither is named here, so pydantic drops them: they are large, they are of
    no use to a browser, and echoing them would put playable audio handles into
    a page.
    """

    model_config = SNOWFLAKE_SAFE

    identifier: str
    title: str
    author: str
    length_ms: int
    is_stream: bool
    uri: str | None = None
    artwork: str | None = None
    isrc: str | None = None
    source: str
    requested_source: str
    played_source: str | None = None
    requester_id: str
    # Stamped by discord-utils from the guild member, so the web never has to
    # resolve a snowflake it cannot see. Empty when the bot could not name them.
    requester_name: str = ""


class SessionOut(BaseModel):
    """One live playback session, as the website renders it.

    `position_ms` is paired with `updated_at` rather than being kept current:
    the browser extrapolates from the two while the track is not paused, so a
    progress bar costs no polling and no server-side timer.
    """

    model_config = SNOWFLAKE_SAFE

    voice_channel_id: str
    guild_id: str | None = None
    channel_name: str | None = None
    bot_index: int | None = None
    nickname: str | None = None
    current: SessionTrack | None = None
    paused: bool = False
    position_ms: int = 0
    updated_at: float = 0.0
    volume: int = 0
    loop: str = "off"
    shuffle: bool = False
    queue_length: int = 0
    remaining_ms: int = 0
    listener_count: int = 0


class SearchResult(TrackIn):
    """One thing a search found.

    Extends the shape a playlist is saved with, so a result can be sent straight
    back to either destination - the queue or a playlist - without the browser
    reshaping it. `encoded` is absent on purpose: the audio is resolved at play
    time, and a browser has no use for a playable handle.
    """

    is_stream: bool = False


class ActivityOut(BaseModel):
    """One recorded interaction with a session."""

    model_config = SNOWFLAKE_SAFE

    at: datetime
    actor_id: str
    # Stamped by discord-utils, for the same reason a track carries its
    # requester's name: nothing on this side can turn a snowflake into a person.
    actor_name: str = ""
    action: str
    detail: str = ""


class HistoryOut(BaseModel):
    """One track that already finished, and how it ended.

    The whole track comes back rather than a rendered line, because the two
    controls on it - queue it again, save it to a playlist - both need the
    metadata. `event` is "played" or "skipped".
    """

    at: datetime
    event: str
    track: SessionTrack
