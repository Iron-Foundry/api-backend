"""Background service that flushes collected outbound HTTP metrics to the DB every 5 minutes."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import MetricRecord

from .collector import OutboundHttpCollector

_FLUSH_INTERVAL = 300
_SERVICE_NAME = "api-backend"
_MODULE_NAME = "outbound_http"


class OutboundMetricsService:
    """Periodically flushes collected outbound HTTP metrics into the metric_records table."""

    def __init__(
        self,
        collector: OutboundHttpCollector,
        session_factory: async_sessionmaker[AsyncSession] | None,
    ) -> None:
        self._collector = collector
        self._session_factory = session_factory
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(
            self._poll_loop(), name="outbound-metrics-flush"
        )
        logger.info("OutboundMetricsService started (interval={}s)", _FLUSH_INTERVAL)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        await self._flush()
        logger.info("OutboundMetricsService stopped")

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
        now = datetime.now(UTC)
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
                "outbound_metrics: flushed {} calls across {} endpoints",
                metrics["total_calls"],
                len(metrics.get("endpoints", {})),
            )
        except Exception as exc:
            logger.warning("outbound_metrics flush error: {}", exc)
