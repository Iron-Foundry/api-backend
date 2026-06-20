"""Periodically snapshots WebSocket connection state into metric_records."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import MetricRecord, ServiceStatus
from app.services.ccingest_metrics import CcIngestMetricsCollector
from app.services.connection_manager import ConnectionManager

_FLUSH_INTERVAL = 60  # 1 minute - fine-grained for coverage graphs
_SERVICE_NAME = "api-backend"
_MODULE_NAME = "websocket"


class WebSocketMetricsService:
    """Snapshots live WebSocket connection counts and ccingest event totals every minute."""

    def __init__(
        self,
        connection_manager: ConnectionManager,
        session_factory: async_sessionmaker[AsyncSession] | None,
        ccingest_collector: CcIngestMetricsCollector | None = None,
    ) -> None:
        self._cm = connection_manager
        self._session_factory = session_factory
        self._ccingest = ccingest_collector
        self._task: asyncio.Task[None] | None = None
        self._start_time = time.monotonic()

    async def start(self) -> None:
        self._task = asyncio.create_task(
            self._poll_loop(), name="websocket-metrics-flush"
        )
        logger.info("WebSocketMetricsService started (interval={}s)", _FLUSH_INTERVAL)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("WebSocketMetricsService stopped")

    async def _poll_loop(self) -> None:
        while True:
            await asyncio.sleep(_FLUSH_INTERVAL)
            await self._flush()

    async def _flush(self) -> None:
        if not self._session_factory:
            return
        now = datetime.now(timezone.utc)
        connected_clients = self._cm.total_connections()
        active_guilds = self._cm.active_guild_count()
        messages_dispatched = self._cm.drain_messages_dispatched()

        metrics: dict = {
            "connected_clients": connected_clients,
            "active_guilds": active_guilds,
            "messages_dispatched": messages_dispatched,
        }

        if self._ccingest is not None:
            ingest = self._ccingest.drain()
            if ingest:
                metrics["ccingest"] = ingest

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
                        uptime_seconds=int(time.monotonic() - self._start_time),
                        summary_metrics=metrics,
                    )
                    .on_conflict_do_update(
                        index_elements=["service_name"],
                        set_={
                            "is_healthy": True,
                            "last_seen": now,
                            "summary_metrics": metrics,
                        },
                    )
                )
                await session.commit()
            logger.debug(
                "websocket_metrics: {} clients, {} guilds, {} dispatched",
                connected_clients,
                active_guilds,
                messages_dispatched,
            )
        except Exception as exc:
            logger.warning("websocket_metrics flush error: {}", exc)
