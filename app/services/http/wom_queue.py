"""WOM API rate-limit priority queue dispatcher.

Single-consumer async queue ensures WOM requests are served in priority order
(HIGH before NORMAL before LOW) while enforcing the 100 req/min budget.

Slot allocation (100 total):
  HIGH   =  5 - always reserved; falls through to NORMAL+LOW if needed
  NORMAL = 20 - reserved for HIGH+NORMAL; falls through to LOW if needed
  LOW    = 75 - base pool, cannot use reserved slots

A priority tier may consume from the tiers below it when its own pool
is exhausted, so effective budgets are:
  HIGH   → remaining               (can use all 100)
  NORMAL → remaining - 5           (can use 95, not HIGH's 5)
  LOW    → remaining - 25          (can use 75, not HIGH+NORMAL's 25)
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Callable

import httpx
from loguru import logger

_HIGH_RESERVE = 5  # slots 96-100: HIGH only
_NORMAL_RESERVE = 20  # slots 76-95: HIGH + NORMAL
_LOW_RESERVE = 75  # slots 1-75:  all priorities


class WomPriority(IntEnum):
    HIGH = 0  # user-triggered (router endpoints)
    NORMAL = 1  # regular background services
    LOW = 2  # bulk / paginated background ops


@dataclass
class WomSnapshot:
    ts: float
    remaining: int
    reserved_used: int
    queue_high: int
    queue_normal: int
    queue_low: int


class _QueueItem:
    __slots__ = ("priority", "seq", "coro_fn", "future")

    def __init__(
        self,
        priority: WomPriority,
        seq: int,
        coro_fn: Callable[[], Any],
        future: asyncio.Future,
    ) -> None:
        self.priority = priority
        self.seq = seq
        self.coro_fn = coro_fn
        self.future = future

    def __lt__(self, other: _QueueItem) -> bool:
        return (self.priority, self.seq) < (other.priority, other.seq)


class WomRequestQueue:
    """Single-consumer priority queue for all WOM API requests."""

    def __init__(self) -> None:
        self._queue: asyncio.PriorityQueue[_QueueItem] = asyncio.PriorityQueue()
        self._seq = 0
        self._task: asyncio.Task[None] | None = None
        self._rl_remaining: int = 100
        self._rl_reset_at: float = 0.0
        self._count: dict[WomPriority, int] = {p: 0 for p in WomPriority}
        self._history: deque[WomSnapshot] = deque(maxlen=720)

    async def start(self) -> None:
        self._task = asyncio.create_task(self._consumer(), name="wom-request-queue")
        logger.info("WomRequestQueue started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("WomRequestQueue stopped")

    def submit(
        self, coro_fn: Callable[[], Any], priority: WomPriority
    ) -> asyncio.Future[httpx.Response]:
        """Enqueue a WOM request. Returns a Future resolved with the httpx.Response."""
        loop = asyncio.get_event_loop()
        future: asyncio.Future[httpx.Response] = loop.create_future()
        seq = self._seq
        self._seq += 1
        self._count[priority] += 1
        self._queue.put_nowait(
            _QueueItem(priority=priority, seq=seq, coro_fn=coro_fn, future=future)
        )
        return future

    def snapshot_history(self) -> list[WomSnapshot]:
        return list(self._history)

    def _effective_remaining(self, priority: WomPriority) -> int:
        if priority == WomPriority.HIGH:
            return self._rl_remaining
        if priority == WomPriority.NORMAL:
            return max(0, self._rl_remaining - _HIGH_RESERVE)
        return max(0, self._rl_remaining - _HIGH_RESERVE - _NORMAL_RESERVE)

    def _rl_update(self, headers: httpx.Headers) -> None:
        raw_remaining = headers.get("ratelimit-remaining")
        raw_reset = headers.get("ratelimit-reset")
        if raw_remaining is not None:
            try:
                self._rl_remaining = int(raw_remaining)
            except ValueError:
                pass
        if raw_reset is not None:
            try:
                self._rl_reset_at = time.monotonic() + float(raw_reset)
            except ValueError:
                pass

    async def _proactive_sleep(self, priority: WomPriority) -> None:
        effective = self._effective_remaining(priority)
        if effective <= 0:
            wait = self._rl_reset_at - time.monotonic()
            if wait > 0:
                logger.debug(
                    "wom: budget low (effective={}, priority={}) - sleeping {:.1f}s",
                    effective,
                    priority.name,
                    wait,
                )
                await asyncio.sleep(wait + 0.25)

    def _record_snapshot(self) -> None:
        self._history.append(
            WomSnapshot(
                ts=time.time(),
                remaining=self._rl_remaining,
                reserved_used=max(
                    0, (_HIGH_RESERVE + _NORMAL_RESERVE) - self._rl_remaining
                ),
                queue_high=self._count[WomPriority.HIGH],
                queue_normal=self._count[WomPriority.NORMAL],
                queue_low=self._count[WomPriority.LOW],
            )
        )

    async def _consumer(self) -> None:
        while True:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                self._record_snapshot()
                continue

            logger.debug(
                "wom: dispatch priority={} seq={} queue=(H:{} N:{} L:{})",
                item.priority.name,
                item.seq,
                self._count[WomPriority.HIGH],
                self._count[WomPriority.NORMAL],
                self._count[WomPriority.LOW],
            )

            await self._proactive_sleep(item.priority)

            try:
                resp = await item.coro_fn()
                self._rl_update(resp.headers)
                if not item.future.done():
                    item.future.set_result(resp)
            except Exception as exc:
                if not item.future.done():
                    item.future.set_exception(exc)
            finally:
                self._count[item.priority] = max(0, self._count[item.priority] - 1)
                self._queue.task_done()

            self._record_snapshot()


_instance: WomRequestQueue | None = None


def init_wom_queue() -> WomRequestQueue:
    global _instance
    _instance = WomRequestQueue()
    return _instance


def get_wom_queue() -> WomRequestQueue:
    if _instance is None:
        raise RuntimeError("WomRequestQueue not initialized - start app lifespan first")
    return _instance
