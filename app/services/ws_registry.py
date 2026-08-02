"""Cluster-wide census of the attached ccdispatch sockets, kept in Valkey.

Every gunicorn worker holds its own in-memory `ConnectionManager`, so no single
process can answer "is this connection attached" or "how many clients are
there". This holds that census in Valkey instead: one sorted set per guild,
member = conn_id, score = the last heartbeat. Readers prune by score first, so a
worker that dies stops counting within the TTL rather than leaking its entries
forever.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable
from typing import cast
from uuid import UUID

from loguru import logger
from valkey.asyncio import Valkey

from app.services.connection_manager import ConnectionManager

CONNS_KEY = "foundry:ws:conns:{guild_id}"
GUILDS_KEY = "foundry:ws:guilds"

_HEARTBEAT_SECONDS = 30
_TTL_SECONDS = 90


def _to_int(value: bytes | str | int) -> int:
    if isinstance(value, bytes):
        return int(value.decode())
    return int(value)


class WsRegistry:
    """Shared view of which sockets are attached, beside the per-worker manager."""

    def __init__(
        self,
        valkey: Valkey,
        connection_manager: ConnectionManager,
        ttl_seconds: int = _TTL_SECONDS,
        interval_seconds: int = _HEARTBEAT_SECONDS,
    ) -> None:
        self._valkey = valkey
        self._cm = connection_manager
        self._ttl = ttl_seconds
        self._interval = interval_seconds
        self._task: asyncio.Task[None] | None = None

    @property
    def valkey(self) -> Valkey:
        return self._valkey

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="ws-registry-heartbeat")
        logger.info(
            "WsRegistry started (heartbeat={}s, ttl={}s)", self._interval, self._ttl
        )

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("WsRegistry stopped")

    async def add(self, guild_id: int, conn_id: UUID) -> None:
        async with self._valkey.pipeline(transaction=True) as pipe:
            pipe.zadd(CONNS_KEY.format(guild_id=guild_id), {str(conn_id): time.time()})
            pipe.sadd(GUILDS_KEY, guild_id)
            await pipe.execute()

    async def remove(self, guild_id: int, conn_id: UUID) -> None:
        await self._valkey.zrem(CONNS_KEY.format(guild_id=guild_id), str(conn_id))

    async def is_connected(self, guild_id: int, conn_id: UUID) -> bool:
        await self._prune(guild_id)
        score = await self._valkey.zscore(
            CONNS_KEY.format(guild_id=guild_id), str(conn_id)
        )
        return score is not None

    async def count(self, guild_id: int) -> int:
        await self._prune(guild_id)
        return int(await self._valkey.zcard(CONNS_KEY.format(guild_id=guild_id)))

    async def totals(self) -> tuple[int, int]:
        """Return (connections, guilds with at least one) across every worker."""
        connections = 0
        active_guilds = 0
        # valkey's async stubs type a few commands as returning the value
        # rather than a coroutine, so these two are cast at the call.
        members = await cast("Awaitable[set[bytes]]", self._valkey.smembers(GUILDS_KEY))
        for raw in members:
            guild_id = _to_int(raw)
            found = await self.count(guild_id)
            if found:
                connections += found
                active_guilds += 1
            else:
                await cast("Awaitable[int]", self._valkey.srem(GUILDS_KEY, guild_id))
        return connections, active_guilds

    async def _prune(self, guild_id: int) -> None:
        await cast(
            "Awaitable[int]",
            self._valkey.zremrangebyscore(
                CONNS_KEY.format(guild_id=guild_id), "-inf", time.time() - self._ttl
            ),
        )

    async def _refresh(self) -> None:
        """Re-score everything this worker holds, so its entries stay alive."""
        held = self._cm.snapshot()
        if not held:
            return
        now = time.time()
        async with self._valkey.pipeline(transaction=False) as pipe:
            for guild_id, conn_ids in held.items():
                pipe.zadd(
                    CONNS_KEY.format(guild_id=guild_id),
                    {str(conn_id): now for conn_id in conn_ids},
                )
                pipe.sadd(GUILDS_KEY, guild_id)
            await pipe.execute()

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            try:
                await self._refresh()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("WsRegistry heartbeat error: {}", exc)
