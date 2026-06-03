"""Collects per-endpoint HTTP metrics and flushes them to metric_records every 5 minutes."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.models import MetricRecord, ServiceStatus

_FLUSH_INTERVAL = 300  # 5 minutes
_SERVICE_NAME = "api-backend"
_MODULE_NAME = "endpoints"


class EndpointMetricsCollector:
    """Lock-free in-memory accumulator for request metrics.

    append() is GIL-atomic for CPython lists so no explicit lock is needed.
    drain() swaps the list atomically before aggregating.
    """

    def __init__(self) -> None:
        self._buf: list[tuple[str, str, int, float, int, int]] = []

    def record(
        self,
        method: str,
        path: str,
        status: int,
        duration_ms: float,
        req_bytes: int = 0,
        resp_bytes: int = 0,
    ) -> None:
        self._buf.append((method, path, status, duration_ms, req_bytes, resp_bytes))

    def drain(self) -> dict:
        buf, self._buf = self._buf, []
        if not buf:
            return {}

        per_endpoint: dict[str, dict] = {}
        for method, path, status, ms, req_b, resp_b in buf:
            key = f"{method} {path}"
            if key not in per_endpoint:
                per_endpoint[key] = {
                    "count": 0,
                    "total_ms": 0.0,
                    "durations": [],
                    "errors_4xx": 0,
                    "errors_5xx": 0,
                    "status_codes": {},
                    "total_req_bytes": 0,
                    "total_resp_bytes": 0,
                }
            s = per_endpoint[key]
            s["count"] += 1
            s["total_ms"] += ms
            s["durations"].append(ms)
            s["total_req_bytes"] += req_b
            s["total_resp_bytes"] += resp_b
            if 400 <= status < 500:
                s["errors_4xx"] += 1
            elif status >= 500:
                s["errors_5xx"] += 1
            code = str(status)
            s["status_codes"][code] = s["status_codes"].get(code, 0) + 1

        total_requests = 0
        total_4xx = 0
        total_5xx = 0
        total_ms = 0.0
        total_req_bytes = 0
        total_resp_bytes = 0
        endpoints: dict[str, dict] = {}

        for key, s in per_endpoint.items():
            n = s["count"]
            sorted_d = sorted(s["durations"])
            p95_idx = max(0, int(n * 0.95) - 1)
            endpoints[key] = {
                "count": n,
                "avg_ms": round(s["total_ms"] / n, 1),
                "p95_ms": round(sorted_d[p95_idx], 1),
                "errors_4xx": s["errors_4xx"],
                "errors_5xx": s["errors_5xx"],
                "status_codes": s["status_codes"],
                "avg_req_bytes": round(s["total_req_bytes"] / n) if n else 0,
                "avg_resp_bytes": round(s["total_resp_bytes"] / n) if n else 0,
                "total_req_bytes": s["total_req_bytes"],
                "total_resp_bytes": s["total_resp_bytes"],
            }
            total_requests += n
            total_4xx += s["errors_4xx"]
            total_5xx += s["errors_5xx"]
            total_ms += s["total_ms"]
            total_req_bytes += s["total_req_bytes"]
            total_resp_bytes += s["total_resp_bytes"]

        return {
            "total_requests": total_requests,
            "total_errors_4xx": total_4xx,
            "total_errors_5xx": total_5xx,
            "avg_latency_ms": round(total_ms / total_requests, 1) if total_requests else 0.0,
            "total_req_bytes": total_req_bytes,
            "total_resp_bytes": total_resp_bytes,
            "endpoints": endpoints,
        }


class EndpointMetricsService:
    """Periodically flushes collected endpoint metrics into the metric_records table."""

    def __init__(self, collector: EndpointMetricsCollector, session_factory) -> None:  # type: ignore[no-untyped-def]
        self._collector = collector
        self._session_factory = session_factory
        self._task: asyncio.Task[None] | None = None
        self._start_time = time.monotonic()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._poll_loop(), name="endpoint-metrics-flush")
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
