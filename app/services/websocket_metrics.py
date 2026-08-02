"""Periodically snapshots WebSocket connection state into metric_records."""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import MetricRecord, ServiceStatus
from app.services.ccingest_metrics import CcIngestMetricsCollector
from app.services.connection_manager import ConnectionManager
from app.services.ws_registry import WsRegistry

_FLUSH_INTERVAL = 60  # 1 minute - fine-grained for coverage graphs
_SERVICE_NAME = "api-backend"
_MODULE_NAME = "websocket"

# Every gunicorn worker runs this service. Without a lease each would write its
# own row holding only its own share, so the graphs showed one worker of three.
# The lease expires just inside the flush interval, so the writer rotates rather
# than sticking to whichever worker won first.
_WRITE_LOCK_KEY = "foundry:ws:metrics_lock"
_WRITE_LOCK_TTL = _FLUSH_INTERVAL - 5
_DISPATCHED_KEY = "foundry:ws:dispatched"


class WebSocketMetricsService:
    """Snapshots live WebSocket connection counts and ccingest event totals every minute."""

    def __init__(
        self,
        connection_manager: ConnectionManager,
        session_factory: async_sessionmaker[AsyncSession] | None,
        ccingest_collector: CcIngestMetricsCollector | None = None,
        registry: WsRegistry | None = None,
        worker_id: str = "",
    ) -> None:
        self._cm = connection_manager
        self._session_factory = session_factory
        self._ccingest = ccingest_collector
        self._registry = registry
        self._worker_id = worker_id or str(os.getpid())
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
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("WebSocketMetricsService stopped")

    async def _poll_loop(self) -> None:
        while True:
            await asyncio.sleep(_FLUSH_INTERVAL)
            await self._flush()

    async def _claim_write(self) -> bool:
        """Win the right to write this interval's row, or defer to the holder."""
        if self._registry is None:
            return True
        won = await self._registry.valkey.set(
            _WRITE_LOCK_KEY, self._worker_id, nx=True, ex=_WRITE_LOCK_TTL
        )
        return bool(won)

    async def _contribute_dispatched(self) -> int:
        """Hand this worker's tally to the shared counter, before any lease.

        Contributing first is what keeps the total conserved: a worker whose
        tick lands after the writer's carries into the next interval rather
        than being dropped, and nothing is ever counted twice.
        """
        local = self._cm.drain_messages_dispatched()
        if self._registry is None or not local:
            return local
        await self._registry.valkey.incrby(_DISPATCHED_KEY, local)
        return local

    async def _take_dispatched(self, local: int) -> int:
        if self._registry is None:
            return local
        return int(await self._registry.valkey.getdel(_DISPATCHED_KEY) or 0)

    async def _flush(self) -> None:
        if not self._session_factory:
            return
        local = await self._contribute_dispatched()
        if not await self._claim_write():
            return

        now = datetime.now(UTC)
        if self._registry is not None:
            connected_clients, active_guilds = await self._registry.totals()
        else:
            connected_clients = self._cm.total_connections()
            active_guilds = self._cm.active_guild_count()
        messages_dispatched = await self._take_dispatched(local)

        metrics: dict[str, Any] = {
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
