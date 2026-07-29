"""Reading a live music session out of Valkey.

discord-utils owns these keys; nothing here writes to them. The session is
ephemeral by design and dies with the bot that serves it, so this reader answers
"what is playing right now" without a database and without a Discord gateway.

The key names and their decoding live in `_live_keys.py`, so a caller that only
needs to name a key does not have to import a reader to get at it.
"""

from __future__ import annotations

import json
from typing import Any

from valkey.asyncio import Valkey

from app.services.valkey_io import resolve

from ._live_keys import (
    ACTIVITY,
    COMMANDS_CHANNEL,
    HISTORY,
    QUEUE,
    QUEUE_PAGE,
    SESSION,
    SESSION_PATTERN,
    VOICE,
    entries,
    mapping,
    text,
)
from ._live_schemas import SessionOut, SessionTrack


async def live_channel_ids(valkey: Valkey) -> list[int]:
    """Every voice channel with a session, newest first is not meaningful here."""
    found = [key async for key in valkey.scan_iter(match=SESSION_PATTERN)]
    return sorted(int(text(key).rsplit(":", 1)[1]) for key in found)


async def read_session(valkey: Valkey, voice_channel_id: int) -> SessionOut | None:
    """One session as the web renders it, or None when nothing is playing there."""
    raw = await resolve(
        valkey.hgetall(SESSION.format(voice_channel_id=voice_channel_id))
    )
    if not raw:
        return None
    data = mapping(raw)

    tracks = await read_queue(valkey, voice_channel_id)
    listeners = await resolve(
        valkey.scard(VOICE.format(voice_channel_id=voice_channel_id))
    )
    return SessionOut(
        voice_channel_id=str(voice_channel_id),
        guild_id=data.get("guild_id"),
        channel_name=data.get("channel_name"),
        bot_index=_optional_int(data.get("bot_index")),
        nickname=data.get("nickname"),
        current=_parse_track(data.get("track")),
        paused=data.get("paused") == "1",
        position_ms=int(data.get("position_ms") or 0),
        updated_at=float(data.get("updated_at") or 0.0),
        volume=int(data.get("volume") or 0),
        loop=data.get("loop") or "off",
        shuffle=data.get("shuffle") == "1",
        queue_length=len(tracks),
        remaining_ms=sum(track.length_ms for track in tracks),
        listener_count=int(listeners or 0),
    )


async def read_queue(valkey: Valkey, voice_channel_id: int) -> list[SessionTrack]:
    """The pending tracks, in the order they will play."""
    raw = await resolve(
        valkey.lrange(
            QUEUE.format(voice_channel_id=voice_channel_id), 0, QUEUE_PAGE - 1
        )
    )
    return [track for track in map(_parse_track, raw) if track is not None]


async def read_activity(
    valkey: Valkey, voice_channel_id: int, limit: int
) -> list[dict[str, Any]]:
    """The recent interactions with a session, newest first."""
    raw = await resolve(
        valkey.lrange(ACTIVITY.format(voice_channel_id=voice_channel_id), 0, limit - 1)
    )
    return entries(raw)


async def read_history(
    valkey: Valkey, voice_channel_id: int, limit: int
) -> list[dict[str, Any]]:
    """What has already played in this session, newest first.

    Unlike the panel, which shows the last ten, the website is given the whole
    kept list: it has the room, and "everything played tonight" is the thing a
    listener actually goes looking for.
    """
    raw = await resolve(
        valkey.lrange(HISTORY.format(voice_channel_id=voice_channel_id), 0, limit - 1)
    )
    return entries(raw)


async def may_control(valkey: Valkey, voice_channel_id: int, user_id: int) -> bool:
    """Whether this user is in the voice channel, and so allowed to drive it.

    The same Valkey set the Discord panel checks, so both surfaces answer the
    question identically and neither can be driven by someone who is not there.
    """
    key = VOICE.format(voice_channel_id=voice_channel_id)
    return bool(await resolve(valkey.sismember(key, str(user_id))))


async def publish_command(valkey: Valkey, command: dict[str, Any]) -> int:
    """Hand an intent to whichever process owns the session."""
    return int(await valkey.publish(COMMANDS_CHANNEL, json.dumps(command)))


def _parse_track(raw: Any) -> SessionTrack | None:
    if not raw:
        return None
    try:
        return SessionTrack.model_validate_json(text(raw))
    except ValueError:
        return None


def _optional_int(value: str | None) -> int | None:
    return int(value) if value else None
