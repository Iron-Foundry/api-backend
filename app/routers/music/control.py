"""Driving a session from the website.

Nothing here plays anything. The command is published onto `music:commands` and
the process holding the Lavalink player executes it, so api-backend never needs
a voice connection and a web control can never do more than a panel button.

Authority is checked twice on purpose - here, so the caller gets a real 403,
and again in discord-utils before the command runs. This side alone would be
trusting whoever published.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from valkey.asyncio import Valkey

from app.dependencies import get_current_user, get_valkey

from ._command_schemas import CommandAccepted, CommandRequest
from ._live import may_control, publish_command, read_session

router = APIRouter(prefix="/sessions")

ValkeyDep = Annotated[Valkey, Depends(get_valkey)]
UserDep = Annotated[dict[str, Any], Depends(get_current_user)]

NO_SESSION = "No music session in that channel"
NOT_IN_CHANNEL = "Join the voice channel to control what it plays"
NOBODY_LISTENING = "No music process is listening for commands"

# What each action cannot run without. Everything else on the body is ignored,
# so a control that gains an argument declares it here and nowhere else.
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "add": ("tracks",),
    "seek": ("position_ms",),
    "shuffle": ("shuffle",),
    "volume": ("volume",),
    "loop": ("loop",),
    "remove": ("index",),
    "jump": ("index",),
    "move": ("index", "destination"),
    "load_playlist": ("playlist_id",),
}


@router.post("/{voice_channel_id}/commands")
async def send_command(
    voice_channel_id: int,
    body: CommandRequest,
    valkey: ValkeyDep,
    current_user: UserDep,
) -> CommandAccepted:
    """Ask the bot serving this channel to do one thing."""
    if await read_session(valkey, voice_channel_id) is None:
        raise HTTPException(status_code=404, detail=NO_SESSION)

    actor_id = int(current_user["sub"])
    if not await may_control(valkey, voice_channel_id, actor_id):
        raise HTTPException(status_code=403, detail=NOT_IN_CHANNEL)

    _require_fields(body)
    delivered = await publish_command(
        valkey, _envelope(body, voice_channel_id, actor_id)
    )
    if delivered == 0:
        # The session hash outlives a crashed process by its TTL, so a live-
        # looking session with no subscriber is a real state, not an impossible
        # one. Saying so beats a silent success.
        raise HTTPException(status_code=503, detail=NOBODY_LISTENING)
    return CommandAccepted(action=body.action, delivered_to=delivered)


def _require_fields(body: CommandRequest) -> None:
    missing = [
        field
        for field in REQUIRED_FIELDS.get(body.action, ())
        if getattr(body, field) is None
    ]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"{body.action} needs {', '.join(missing)}",
        )


def _envelope(
    body: CommandRequest, voice_channel_id: int, actor_id: int
) -> dict[str, Any]:
    """The published command. Pause and resume are one action with a flag.

    discord-utils takes `paused` rather than two verbs because the transport
    call is `player.pause(bool)`; splitting it on the web is only so a button
    can name what it does.
    """
    command: dict[str, Any] = {
        "voice_channel_id": voice_channel_id,
        "actor_id": actor_id,
        "action": "pause" if body.action == "resume" else body.action,
    }
    if body.action in {"pause", "resume"}:
        command["paused"] = body.action == "pause"
    for field in ("index", "destination", "position_ms", "volume", "loop", "shuffle"):
        value = getattr(body, field)
        if value is not None:
            command[field] = value
    if body.playlist_id is not None:
        command["playlist_id"] = body.playlist_id
    if body.tracks is not None:
        command["tracks"] = [track.model_dump() for track in body.tracks]
    return command
