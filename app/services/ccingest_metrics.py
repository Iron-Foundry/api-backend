"""Collects per-event-type ccingest metrics and flushes them to metric_records every 5 minutes."""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.models import MetricRecord

_FLUSH_INTERVAL = 300  # 5 minutes
_SERVICE_NAME = "api-backend"
_MODULE_NAME = "ccingest"


class CcIngestMetricsCollector:
    """Lock-free in-memory accumulator for ccingest event type counts.

    record() appends a string - GIL-atomic for CPython lists.
    drain() swaps the buffer atomically before aggregating.
    """

    def __init__(self) -> None:
        self._buf: list[str] = []

    def record(self, event_type: str) -> None:
        self._buf.append(event_type)

    def drain(self) -> dict:
        buf, self._buf = self._buf, []
        if not buf:
            return {}
        counts: Counter[str] = Counter(buf)
        duplicates = counts.pop("duplicate", 0)
        total = sum(counts.values())
        return {
            "total_messages": total,
            "duplicate_skipped": duplicates,
            **dict(counts),
        }


class CcIngestMetricsService:
    """Periodically flushes ccingest event counts into metric_records."""

    def __init__(self, collector: CcIngestMetricsCollector, session_factory) -> None:  # type: ignore[no-untyped-def]
        self._collector = collector
        self._session_factory = session_factory
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(
            self._poll_loop(), name="ccingest-metrics-flush"
        )
        logger.info("CcIngestMetricsService started (interval={}s)", _FLUSH_INTERVAL)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._flush()
        logger.info("CcIngestMetricsService stopped")

    async def _poll_loop(self) -> None:
        while True:
            await asyncio.sleep(_FLUSH_INTERVAL)
            await self._flush()

    async def _flush(self) -> None:
        if not self._session_factory:
            return
        metrics = self._collector.drain()
        if not metrics:
            return
        now = datetime.now(timezone.utc)
        try:
            async with self._session_factory() as session:
                await session.execute(
                    pg_insert(MetricRecord).values(
                        service_name=_SERVICE_NAME,
                        module_name=_MODULE_NAME,
                        recorded_at=now,
                        metrics=metrics,
                    )
                )
                await session.commit()
            logger.debug(
                "ccingest_metrics: flushed {} messages",
                metrics.get("total_messages", 0),
            )
        except Exception as exc:
            logger.warning("ccingest_metrics flush error: {}", exc)


collector = CcIngestMetricsCollector()
