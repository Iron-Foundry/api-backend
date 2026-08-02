"""Fans a dispatched clan-chat message out to whichever worker holds the socket.

`POST /ccdispatch` is served by one gunicorn worker, but the RuneLite sockets
are spread across all of them and each worker's `ConnectionManager` only knows
its own. The endpoint therefore publishes here rather than broadcasting, and
this subscriber - which runs in every worker - does the delivery.

This is deliberately its own channel rather than `foundry:discord_chat`: that
one's consumer also runs the spacebar-check accounting, which a dispatched
message has no business tripping.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any
from uuid import UUID

from loguru import logger
from valkey.asyncio import Valkey

from app.services.connection_manager import ConnectionManager

CC_DISPATCH_CHANNEL = "foundry:ccdispatch"

_RECONNECT_SECONDS = 5


class CcDispatchService:
    """Subscribes to the dispatch channel and delivers to this worker's clients.

    `manager` defaults to the process-wide singleton, which is what a real
    worker uses. Tests pass their own so several workers can be stood up side by
    side against one Valkey - the only way to observe that a publish reaches
    whichever worker actually holds the socket.
    """

    def __init__(
        self, valkey_uri: str, manager: ConnectionManager | None = None
    ) -> None:
        self._valkey_uri = valkey_uri
        self._manager = manager
        self._task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="cc-dispatch-subscriber")
        logger.info("CcDispatchService started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("CcDispatchService stopped")

    async def _run(self) -> None:
        while True:
            # A blocking listen needs its own connection with no socket timeout,
            # or the shared client's timeout kills the subscriber silently.
            sub = Valkey.from_url(self._valkey_uri, socket_timeout=None)
            try:
                async with sub.pubsub() as ps:
                    await ps.subscribe(CC_DISPATCH_CHANNEL)
                    logger.info(
                        "CcDispatchService: subscribed to {}", CC_DISPATCH_CHANNEL
                    )
                    async for raw in ps.listen():
                        if raw["type"] != "message":
                            continue
                        try:
                            await deliver(json.loads(raw["data"]), self._manager)
                        except Exception as exc:
                            logger.warning("CcDispatchService error: {}", exc)
            except asyncio.CancelledError:
                logger.info("CcDispatchService: shutting down")
                await sub.aclose()
                return
            except Exception as exc:
                logger.warning(
                    "CcDispatchService: connection lost ({}), reconnecting in {}s",
                    exc,
                    _RECONNECT_SECONDS,
                )
                await sub.aclose()
                await asyncio.sleep(_RECONNECT_SECONDS)


async def deliver(
    data: dict[str, Any], manager: ConnectionManager | None = None
) -> None:
    """Send one published dispatch to the sockets this worker holds.

    Every worker runs this for every publish. When the payload names a
    connection only its owner delivers; the others find nothing and do nothing.
    """
    from app.routers.ccdispatch import split_message, wrap_message
    from app.services.connection_manager import connection_manager

    target = manager if manager is not None else connection_manager
    guild_id = int(data["guild_id"])
    raw_conn_id = data.get("conn_id")
    conn_id = UUID(raw_conn_id) if raw_conn_id else None

    for part in split_message(data["message"]):
        message = wrap_message(data["sender"], part, data.get("rank"))
        if conn_id is not None:
            await target.send_to(conn_id, guild_id, message)
        else:
            await target.broadcast(guild_id, message)
