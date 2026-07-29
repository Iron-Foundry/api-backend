"""Consuming the music event stream into the clan counters.

A Valkey stream with a consumer group, not pubsub. Playback must never block on
a database write, and an api-backend restart must not lose what happened while
it was down - a consumer group picks up from where it stopped, where pubsub
would simply have dropped it.

The stream mechanics and the at-least-once handling are in `music_stream.py`.
What is here is the loop, the transaction, and the connection it all runs on.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

from app.services import music_stream as stream
from app.services.music_counters import apply_event

BLOCK_MS = 5_000
RECONNECT_SECONDS = 5

SessionFactory = Callable[[], AsyncSession]


class MusicStatsService:
    """Reads `music:events` and turns it into the anonymous counters."""

    def __init__(
        self,
        valkey_uri: str,
        session_factory: SessionFactory | None,
        *,
        valkey: Valkey | None = None,
    ) -> None:
        self._valkey_uri = valkey_uri
        self._injected = valkey
        self._owned: Valkey | None = None
        self._session_factory = session_factory
        self._task: asyncio.Task[None] | None = None

    @property
    def valkey(self) -> Valkey:
        """A connection of its own, built to allow a blocking read.

        Never the request client. A blocking `XREADGROUP` holds its socket for
        as long as it blocks, and the shared client carries a socket timeout far
        shorter than that - which turned every poll into a timeout and the whole
        consumer into a retry loop that counted nothing. Same reasoning as the
        pubsub connection in `music_live.py`.
        """
        if self._injected is not None:
            return self._injected
        if self._owned is None:
            self._owned = Valkey.from_url(self._valkey_uri, socket_timeout=None)
        return self._owned

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self._session_factory is None:
            logger.info("MusicStatsService: no database configured, not starting")
            return
        await self.ensure_group()
        self._task = asyncio.create_task(self._run(), name="music-stats-consumer")
        logger.info("MusicStatsService started")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._owned is not None:
            await self._owned.aclose()
            self._owned = None
        logger.info("MusicStatsService stopped")

    async def ensure_group(self) -> None:
        await stream.ensure_group(self.valkey)

    async def consume_once(self, block_ms: int | None = None) -> int:
        """One poll: whatever is pending first, then whatever is new.

        Pending is read before new so a batch left behind by a worker that died
        mid-transaction is retried rather than sitting in the group forever.
        """
        messages = await stream.read(self.valkey, "0", None)
        if not messages:
            messages = await stream.read(self.valkey, ">", block_ms)
        if not messages:
            return 0

        fresh = [
            (mid, body)
            for mid, body in messages
            if await stream.claim(self.valkey, mid)
        ]
        try:
            await self._count(fresh)
        except Exception:
            await stream.release(self.valkey, [mid for mid, _ in fresh])
            raise
        await stream.ack(self.valkey, [mid for mid, _ in messages])
        return len(messages)

    async def _count(self, messages: list[stream.Message]) -> None:
        if not messages or self._session_factory is None:
            return
        async with self._session_factory() as session:
            for _, body in messages:
                await apply_event(session, stream.fields(body))
            await session.commit()

    async def _run(self) -> None:
        while True:
            try:
                await self.consume_once(BLOCK_MS)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning(
                    "MusicStatsService: {}, retrying in {}s", exc, RECONNECT_SECONDS
                )
                await asyncio.sleep(RECONNECT_SECONDS)
