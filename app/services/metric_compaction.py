"""Background service that compacts metric_records older than 3 months into daily aggregates."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Any

from loguru import logger
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.models import MetricRecord, MetricRecordCompact

_RETENTION_DAYS = 90
_POLL_INTERVAL = 86400  # run once per day
_BATCH_SIZE = 10000


def _aggregate_metrics(rows: list[dict]) -> dict[str, Any]:
    """Compute min/max/avg/sum/count for each numeric key across a list of metric dicts."""
    agg: dict[str, dict[str, Any]] = {}
    for metrics in rows:
        for key, val in metrics.items():
            if not isinstance(val, (int, float)):
                continue
            if key not in agg:
                agg[key] = {"min": val, "max": val, "sum": val, "count": 1}
            else:
                bucket = agg[key]
                bucket["min"] = min(bucket["min"], val)
                bucket["max"] = max(bucket["max"], val)
                bucket["sum"] += val
                bucket["count"] += 1
    for key in agg:
        agg[key]["avg"] = agg[key]["sum"] / agg[key]["count"]
    return agg


class MetricCompactionService:
    """Compacts raw metric_records older than 3 months into daily aggregates."""

    def __init__(self, session_factory) -> None:  # type: ignore[no-untyped-def]
        self._session_factory = session_factory
        self._task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._poll_loop(), name="metric-compaction")
        logger.info("MetricCompactionService started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("MetricCompactionService stopped")

    async def run_now(self) -> int:
        """Compact eligible records immediately. Returns number of raw records deleted."""
        if not self._session_factory:
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=_RETENTION_DAYS)
        deleted = 0
        try:
            async with self._session_factory() as session:
                groups_result = await session.execute(
                    select(
                        MetricRecord.service_name,
                        MetricRecord.module_name,
                        func.date_trunc("day", MetricRecord.recorded_at).label("day"),
                    )
                    .where(MetricRecord.recorded_at < cutoff)
                    .group_by(
                        MetricRecord.service_name,
                        MetricRecord.module_name,
                        func.date_trunc("day", MetricRecord.recorded_at),
                    )
                )
                groups = groups_result.all()

            for service_name, module_name, day_dt in groups:
                day: date = day_dt.date() if hasattr(day_dt, "date") else day_dt
                day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
                day_end = day_start + timedelta(days=1)

                async with self._session_factory() as session:
                    raw_result = await session.execute(
                        select(MetricRecord.metrics)
                        .where(
                            MetricRecord.service_name == service_name,
                            MetricRecord.module_name == module_name,
                            MetricRecord.recorded_at >= day_start,
                            MetricRecord.recorded_at < day_end,
                        )
                        .limit(_BATCH_SIZE)
                    )
                    raw_metrics = [row[0] for row in raw_result]

                    if not raw_metrics:
                        continue

                    metrics_agg = _aggregate_metrics(raw_metrics)
                    await session.execute(
                        pg_insert(MetricRecordCompact)
                        .values(
                            service_name=service_name,
                            module_name=module_name,
                            date=day,
                            sample_count=len(raw_metrics),
                            metrics_agg=metrics_agg,
                        )
                        .on_conflict_do_update(
                            constraint="uq_metric_compact_day",
                            set_={
                                "sample_count": len(raw_metrics),
                                "metrics_agg": metrics_agg,
                            },
                        )
                    )

                    del_result = await session.execute(
                        delete(MetricRecord).where(
                            MetricRecord.service_name == service_name,
                            MetricRecord.module_name == module_name,
                            MetricRecord.recorded_at >= day_start,
                            MetricRecord.recorded_at < day_end,
                        )
                    )
                    deleted += del_result.rowcount
                    await session.commit()

            logger.info("MetricCompactionService: compacted {} raw records", deleted)
        except Exception as exc:
            logger.warning("MetricCompactionService error: {}", exc)
        return deleted

    async def _poll_loop(self) -> None:
        while True:
            await asyncio.sleep(_POLL_INTERVAL)
            await self.run_now()
