"""Background service that flushes collected endpoint metrics to the DB every 5 minutes."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.models import MetricRecord, ServiceStatus
from .collector import EndpointMetricsCollector

_FLUSH_INTERVAL = 300  # 5 minutes
_SERVICE_NAME = "api-backend"
_MODULE_NAME = "endpoints"


class EndpointMetricsService:
    """Periodically flushes collected endpoint metrics into the metric_records table."""

    def __init__(self, collector: EndpointMetricsCollector, session_factory) -> None:  # type: ignore[no-untyped-def]
        self._collector = collector
        self._session_factory = session_factory
        self._task: asyncio.Task[None] | None = None
        self._start_time = time.monotonic()

    async def start(self) -> None:
        self._task = asyncio.create_task(
            self._poll_loop(), name="endpoint-metrics-flush"
        )
        logger.info("EndpointMetricsService started (interval={}s)", _FLUSH_INTERVAL)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._flush()
        logger.info("EndpointMetricsService stopped")

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
        uptime = int(time.monotonic() - self._start_time)
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
                await session.execute(
                    pg_insert(ServiceStatus)
                    .values(
                        service_name=_SERVICE_NAME,
                        is_healthy=True,
                        last_seen=now,
                        version=None,
                        uptime_seconds=uptime,
                        summary_metrics={
                            "total_requests": metrics["total_requests"],
                            "total_errors_4xx": metrics["total_errors_4xx"],
                            "total_errors_5xx": metrics["total_errors_5xx"],
                            "avg_latency_ms": metrics["avg_latency_ms"],
                        },
                    )
                    .on_conflict_do_update(
                        index_elements=["service_name"],
                        set_={
                            "is_healthy": True,
                            "last_seen": now,
                            "uptime_seconds": uptime,
                            "summary_metrics": {
                                "total_requests": metrics["total_requests"],
                                "total_errors_4xx": metrics["total_errors_4xx"],
                                "total_errors_5xx": metrics["total_errors_5xx"],
                                "avg_latency_ms": metrics["avg_latency_ms"],
                            },
                        },
                    )
                )
                await session.commit()
            logger.debug(
                "endpoint_metrics: flushed {} requests across {} endpoints",
                metrics["total_requests"],
                len(metrics.get("endpoints", {})),
            )
        except Exception as exc:
            logger.warning("endpoint_metrics flush error: {}", exc)
