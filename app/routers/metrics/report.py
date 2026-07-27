from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from loguru import logger
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MetricRecord, ServiceStatus
from app.dependencies import get_session, verify_metrics_key

from ._helpers import MetricReportBody

router = APIRouter()


@router.post("/metrics/report")
async def report_metrics(
    body: MetricReportBody,
    _key: None = Depends(verify_metrics_key),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Upsert service status and append a time-series record."""
    now = datetime.now(UTC)

    await session.execute(
        pg_insert(MetricRecord).values(
            service_name=body.service_name,
            module_name=body.module_name,
            recorded_at=now,
            metrics=body.metrics,
        )
    )

    await session.execute(
        pg_insert(ServiceStatus)
        .values(
            service_name=body.service_name,
            is_healthy=body.is_healthy,
            last_seen=now,
            version=body.version,
            uptime_seconds=body.uptime_seconds,
            summary_metrics=body.metrics,
        )
        .on_conflict_do_update(
            index_elements=["service_name"],
            set_={
                "is_healthy": body.is_healthy,
                "last_seen": now,
                "version": body.version,
                "uptime_seconds": body.uptime_seconds,
                "summary_metrics": body.metrics,
            },
        )
    )

    await session.commit()
    logger.debug("metrics/report: {}/{}", body.service_name, body.module_name)
    return {"ok": True}
