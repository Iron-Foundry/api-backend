"""The live music socket.

Authentication happens in the first frame rather than in a header or a query
string: a browser cannot set headers on a WebSocket, and a token in the URL
would be written into every access log that records the path.

The socket is read-only. Controls go through `POST /music/sessions/{id}/commands`
so that one code path validates them, whichever surface they came from.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from app.dependencies import decode_token
from app.services.music_live import music_hub

from ._live import live_channel_ids, read_session

router = APIRouter()

AUTH_TIMEOUT_SECONDS = 10
UNAUTHORISED = 1008

# A client that says nothing and a client that vanishes are the same outcome:
# no token arrived, so the socket closes.
HANDSHAKE_FAILURES = (TimeoutError, WebSocketDisconnect)


@router.websocket("/live")
async def music_live(websocket: WebSocket) -> None:
    """Watch every live session.

    Send `{"type": "auth", "token": "<jwt>"}` first. The reply is a `sessions`
    snapshot, and after that a `session` frame whenever one moves and a `closed`
    frame when one ends.
    """
    await websocket.accept()
    if not await _authenticate(websocket):
        await websocket.close(code=UNAUTHORISED)
        return

    valkey = websocket.app.state.valkey
    sessions = [
        await read_session(valkey, channel_id)
        for channel_id in await live_channel_ids(valkey)
    ]
    await websocket.send_json(
        {
            "type": "sessions",
            "sessions": [
                session.model_dump(mode="json")
                for session in sessions
                if session is not None
            ],
        }
    )

    socket_id = music_hub.connect(websocket)
    try:
        # Nothing is expected from the client after the handshake, but the read
        # has to stay open or the disconnect is never noticed.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("Music socket closed unexpectedly: {}", exc)
    finally:
        music_hub.disconnect(socket_id)


async def _authenticate(websocket: WebSocket) -> bool:
    """Read the first frame and check the token it carries."""
    try:
        raw = await asyncio.wait_for(
            websocket.receive_text(), timeout=AUTH_TIMEOUT_SECONDS
        )
    except HANDSHAKE_FAILURES:
        return False

    try:
        frame = json.loads(raw)
    except ValueError:
        return False
    if frame.get("type") != "auth" or not isinstance(frame.get("token"), str):
        return False
    return decode_token(frame["token"]) is not None
