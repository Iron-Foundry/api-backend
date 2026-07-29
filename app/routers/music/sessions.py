"""What is playing right now, read straight from Valkey.

Nothing here touches Postgres. A session exists only while a bot is in a voice
channel, so the live surface is read from the same ephemeral keys the Discord
panel renders from - which is what keeps the two surfaces from disagreeing.

Reading is open to any signed-in member. Driving playback is not; see
`control.py`.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from valkey.asyncio import Valkey

from app.dependencies import get_current_user, get_valkey

from ._live import (
    live_channel_ids,
    may_control,
    read_activity,
    read_history,
    read_queue,
    read_session,
)
from ._live_schemas import ActivityOut, HistoryOut, SessionOut, SessionTrack

router = APIRouter(prefix="/sessions")

ValkeyDep = Annotated[Valkey, Depends(get_valkey)]
UserDep = Annotated[dict[str, Any], Depends(get_current_user)]

ACTIVITY_LIMIT = 25
# Mirrors HISTORY_LIMIT in discord-utils: the cap on what the bot keeps, so the
# website's default is the whole list rather than a page of it.
HISTORY_LIMIT = 100
NO_SESSION = "No music session in that channel"


@router.get("")
async def list_sessions(valkey: ValkeyDep, current_user: UserDep) -> list[SessionOut]:
    """Every live session, so the website can offer a channel to watch."""
    sessions = [
        await read_session(valkey, channel_id)
        for channel_id in await live_channel_ids(valkey)
    ]
    return [session for session in sessions if session is not None]


@router.get("/{voice_channel_id}")
async def get_session(
    voice_channel_id: int, valkey: ValkeyDep, current_user: UserDep
) -> SessionOut:
    """One session, or 404 once its bot has left the channel."""
    return await _require_session(valkey, voice_channel_id)


@router.get("/{voice_channel_id}/queue")
async def get_queue(
    voice_channel_id: int, valkey: ValkeyDep, current_user: UserDep
) -> list[SessionTrack]:
    """The pending tracks in play order."""
    await _require_session(valkey, voice_channel_id)
    return await read_queue(valkey, voice_channel_id)


@router.get("/{voice_channel_id}/activity")
async def get_activity(
    voice_channel_id: int,
    valkey: ValkeyDep,
    current_user: UserDep,
    limit: Annotated[int, Query(ge=1, le=ACTIVITY_LIMIT)] = ACTIVITY_LIMIT,
) -> list[ActivityOut]:
    """Who did what to this session, newest first."""
    await _require_session(valkey, voice_channel_id)
    entries = await read_activity(valkey, voice_channel_id, limit)
    return [ActivityOut.model_validate(entry) for entry in entries]


@router.get("/{voice_channel_id}/history")
async def get_history(
    voice_channel_id: int,
    valkey: ValkeyDep,
    current_user: UserDep,
    limit: Annotated[int, Query(ge=1, le=HISTORY_LIMIT)] = HISTORY_LIMIT,
) -> list[HistoryOut]:
    """What has already played here, newest first.

    The panel shows the last ten; this returns everything the bot still keeps,
    which is what the website's re-queue and save-to-playlist controls act on.
    """
    await _require_session(valkey, voice_channel_id)
    entries = await read_history(valkey, voice_channel_id, limit)
    return [HistoryOut.model_validate(entry) for entry in entries]


@router.get("/{voice_channel_id}/control")
async def get_control(
    voice_channel_id: int, valkey: ValkeyDep, current_user: UserDep
) -> dict[str, bool]:
    """Whether the caller may drive this session.

    Its own endpoint rather than a field on the session: the session payload is
    broadcast to every watcher over the socket, and this answer differs per
    viewer.
    """
    allowed = await may_control(valkey, voice_channel_id, int(current_user["sub"]))
    return {"may_control": allowed}


async def _require_session(valkey: Valkey, voice_channel_id: int) -> SessionOut:
    session = await read_session(valkey, voice_channel_id)
    if session is None:
        raise HTTPException(status_code=404, detail=NO_SESSION)
    return session
