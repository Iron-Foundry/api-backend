"""Pushing frenzy draft changes to the watching draft pages.

A route that changes a draft publishes the event id on `frenzy:draft`. Each
gunicorn worker subscribes and tells its own sockets, so a watcher on any
worker hears a pick made on any other. The frame carries only the event id:
the page refetches the draft view, so the socket and the route never disagree.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from uuid import UUID, uuid4

from fastapi import WebSocket
from loguru import logger
from valkey.asyncio import Valkey

DRAFT_CHANNEL = "frenzy:draft"
RECONNECT_SECONDS = 5


class DraftLiveHub:
    """The sockets of this worker that watch a frenzy draft."""

    def __init__(self) -> None:
        self._sockets: dict[UUID, WebSocket] = {}

    def connect(self, websocket: WebSocket) -> UUID:
        socket_id = uuid4()
        self._sockets[socket_id] = websocket
        return socket_id

    def disconnect(self, socket_id: UUID) -> None:
        self._sockets.pop(socket_id, None)

    async def broadcast(self, event_id: int) -> None:
        message = json.dumps({"type": "draft", "event_id": event_id})
        dead: list[UUID] = []
        for socket_id, websocket in list(self._sockets.items()):
            try:
                await websocket.send_text(message)
            except Exception:
                dead.append(socket_id)
        for socket_id in dead:
            self.disconnect(socket_id)


draft_hub = DraftLiveHub()


async def publish_draft_change(valkey: Valkey, event_id: int) -> None:
    await valkey.publish(DRAFT_CHANNEL, json.dumps({"event_id": event_id}))


class DraftLiveService:
    """Subscribes to `frenzy:draft` and fans each change out to this worker's sockets."""

    def __init__(self, valkey_uri: str) -> None:
        self._valkey_uri = valkey_uri
        self._task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="frenzy-draft-subscriber")
        logger.info("DraftLiveService started")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        logger.info("DraftLiveService stopped")

    async def handle(self, raw: str | bytes) -> None:
        try:
            event_id = int(json.loads(raw)["event_id"])
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("DraftLiveService: unreadable notice {!r}: {}", raw, exc)
            return
        await draft_hub.broadcast(event_id)

    async def _run(self) -> None:
        while True:
            sub = Valkey.from_url(self._valkey_uri, socket_timeout=None)
            try:
                async with sub.pubsub() as ps:
                    await ps.subscribe(DRAFT_CHANNEL)
                    logger.info("DraftLiveService: subscribed to {}", DRAFT_CHANNEL)
                    async for message in ps.listen():
                        if message["type"] == "message":
                            await self.handle(message["data"])
            except asyncio.CancelledError:
                await sub.aclose()
                return
            except Exception as exc:
                logger.warning(
                    "DraftLiveService: connection lost ({}), reconnecting in {}s",
                    exc,
                    RECONNECT_SECONDS,
                )
                await sub.aclose()
                await asyncio.sleep(RECONNECT_SECONDS)
