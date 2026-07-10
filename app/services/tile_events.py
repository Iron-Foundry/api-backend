"""Valkey pub/sub event bus streaming real-time tile activity to SSE clients.

Publishing goes through the shared Valkey client so events fan out to every
worker; each SSE connection opens its own subscriber connection.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

from valkey.asyncio import Valkey

_CHANNEL = "foundry:tile_events"
_HEARTBEAT_INTERVAL = 15.0


class TileEventBus:
    """Fan-out event bus backed by Valkey pub/sub, safe across multiple workers."""

    def __init__(self, valkey_uri: str, valkey: Valkey) -> None:
        self._uri = valkey_uri
        self._valkey = valkey

    async def publish(self, event_type: str, **data: object) -> None:
        payload = json.dumps({"type": event_type, **data})
        await self._valkey.publish(_CHANNEL, payload)

    async def stream(self) -> AsyncGenerator[str, None]:
        """Yield SSE frames from the tile-events channel, with idle heartbeats."""
        sub = Valkey.from_url(self._uri)
        try:
            async with sub.pubsub() as ps:
                await ps.subscribe(_CHANNEL)
                while True:
                    msg = await ps.get_message(
                        ignore_subscribe_messages=True,
                        timeout=_HEARTBEAT_INTERVAL,
                    )
                    if msg is None:
                        yield ": heartbeat\n\n"
                        continue
                    data = msg["data"]
                    if isinstance(data, bytes):
                        data = data.decode()
                    yield f"data: {data}\n\n"
        finally:
            await sub.aclose()
