"""Persists WOM rate-limit snapshots from the in-memory ring buffer to metric_records."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import MetricRecord
from app.services.http.wom_queue import get_wom_queue

_FLUSH_INTERVAL = 30
_SERVICE_NAME = "api-backend"
_MODULE_NAME = "wom_rate_limit"


class WomMetricsService:
    """Flushes new WOM queue snapshots to the DB every 30 seconds."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession] | None
    ) -> None:
        self._session_factory = session_factory
        self._task: asyncio.Task[None] | None = None
        self._last_flushed_ts: float = 0.0

    async def start(self) -> None:
        self._task = asyncio.create_task(self._poll_loop(), name="wom-metrics-flush")
        logger.info("WomMetricsService started (interval={}s)", _FLUSH_INTERVAL)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("WomMetricsService stopped")

    async def _poll_loop(self) -> None:
        while True:
            await asyncio.sleep(_FLUSH_INTERVAL)
            await self._flush()

    async def _flush(self) -> None:
        if not self._session_factory:
            return
        new_snapshots = [
            s
            for s in get_wom_queue().snapshot_history()
            if s.ts > self._last_flushed_ts
        ]
        if not new_snapshots:
            return
        try:
            async with self._session_factory() as session:
                for s in new_snapshots:
                    await session.execute(
                        pg_insert(MetricRecord).values(
                            service_name=_SERVICE_NAME,
                            module_name=_MODULE_NAME,
                            recorded_at=datetime.fromtimestamp(s.ts, tz=UTC),
                            metrics={
                                "remaining": s.remaining,
                                "reserved_used": s.reserved_used,
                                "queue_high": s.queue_high,
                                "queue_normal": s.queue_normal,
                                "queue_low": s.queue_low,
                            },
                        )
                    )
                await session.commit()
            self._last_flushed_ts = new_snapshots[-1].ts
            logger.debug("wom_metrics: flushed {} snapshots to DB", len(new_snapshots))
        except Exception as exc:
            logger.warning("wom_metrics flush error: {}", exc)
