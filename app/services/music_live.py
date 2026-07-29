"""Pushing live music state to the website.

discord-utils publishes a bare notice on `music:state` naming the channel that
moved. This service reads that channel's session out of Valkey and broadcasts
the same payload the REST route returns, so the socket and the endpoint can
never describe a session differently.

Every watcher receives every session. There are at most five, the payload is
small, and it means a page can render both the player it is watching and the
mini bar for whatever else is live without a subscription protocol.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any
from uuid import UUID, uuid4

from fastapi import WebSocket
from loguru import logger
from valkey.asyncio import Valkey

RECONNECT_SECONDS = 5


class MusicLiveHub:
    """The sockets currently watching music state."""

    def __init__(self) -> None:
        self._sockets: dict[UUID, WebSocket] = {}

    def connect(self, websocket: WebSocket) -> UUID:
        socket_id = uuid4()
        self._sockets[socket_id] = websocket
        return socket_id

    def disconnect(self, socket_id: UUID) -> None:
        self._sockets.pop(socket_id, None)

    @property
    def watcher_count(self) -> int:
        return len(self._sockets)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        message = json.dumps(payload, default=str)
        dead: list[UUID] = []
        for socket_id, websocket in list(self._sockets.items()):
            try:
                await websocket.send_text(message)
            except Exception:
                dead.append(socket_id)
        for socket_id in dead:
            self.disconnect(socket_id)


music_hub = MusicLiveHub()


class MusicStateService:
    """Subscribes to `music:state` and fans it out to the watching pages."""

    def __init__(self, valkey_uri: str, valkey: Valkey) -> None:
        self._valkey_uri = valkey_uri
        self._valkey = valkey
        self._task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="music-state-subscriber")
        logger.info("MusicStateService started")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        logger.info("MusicStateService stopped")

    async def handle(self, raw: str | bytes) -> None:
        """Turn one notice into the payload the page renders."""
        from app.routers.music._live import read_session

        try:
            notice = json.loads(raw)
            voice_channel_id = int(notice["voice_channel_id"])
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("MusicStateService: unreadable notice {!r}: {}", raw, exc)
            return

        if notice.get("event") == "closed":
            await music_hub.broadcast(
                {"type": "closed", "voice_channel_id": voice_channel_id}
            )
            return

        session = await read_session(self._valkey, voice_channel_id)
        if session is None:
            # The keys expired between the notice and this read, which is the
            # same thing as the session having ended.
            await music_hub.broadcast(
                {"type": "closed", "voice_channel_id": voice_channel_id}
            )
            return
        await music_hub.broadcast(
            {"type": "session", "session": session.model_dump(mode="json")}
        )

    async def _run(self) -> None:
        from app.routers.music._live_keys import STATE_CHANNEL

        while True:
            sub = Valkey.from_url(self._valkey_uri, socket_timeout=None)
            try:
                async with sub.pubsub() as ps:
                    await ps.subscribe(STATE_CHANNEL)
                    logger.info("MusicStateService: subscribed to {}", STATE_CHANNEL)
                    async for message in ps.listen():
                        if message["type"] == "message":
                            await self.handle(message["data"])
            except asyncio.CancelledError:
                await sub.aclose()
                return
            except Exception as exc:
                logger.warning(
                    "MusicStateService: connection lost ({}), reconnecting in {}s",
                    exc,
                    RECONNECT_SECONDS,
                )
                await sub.aclose()
                await asyncio.sleep(RECONNECT_SECONDS)
