from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MetricRecord, MetricRecordCompact
from app.dependencies import get_current_user, get_session

from ._helpers import require_staff

router = APIRouter()

_SUM_KEYS = {
    "total_requests",
    "errors_4xx",
    "errors_5xx",
    "total_req_bytes",
    "total_resp_bytes",
    "messages_dispatched",
    "closed_today",
}


def _flatten_compact_metrics(metrics_agg: dict) -> dict:
    """Flatten compact {min,max,avg,sum,count} metrics to scalar values for frontend compatibility."""
    result = {}
    for key, val in metrics_agg.items():
        if isinstance(val, dict) and "avg" in val:
            result[key] = val["sum"] if key in _SUM_KEYS else val["avg"]
        else:
            result[key] = val
    return result


@router.get("/metrics/bandwidth")
async def metrics_bandwidth(
    service: str = Query(default="api-backend"),
    module: str = Query(default="endpoints"),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return all-time total request and response bytes for a service/module pair."""
    await require_staff(current_user, session)

    raw = await session.execute(
        text(
            """
            SELECT
                COALESCE(SUM((metrics->>'total_req_bytes')::bigint), 0),
                COALESCE(SUM((metrics->>'total_resp_bytes')::bigint), 0)
            FROM metric_records
            WHERE service_name = :svc AND module_name = :mod
              AND metrics ? 'total_req_bytes'
            """
        ),
        {"svc": service, "mod": module},
    )
    raw_req, raw_resp = raw.one()

    compact = await session.execute(
        text(
            """
            SELECT
                COALESCE(SUM((metrics_agg->'total_req_bytes'->>'sum')::bigint), 0),
                COALESCE(SUM((metrics_agg->'total_resp_bytes'->>'sum')::bigint), 0)
            FROM metric_records_compact
            WHERE service_name = :svc AND module_name = :mod
              AND metrics_agg ? 'total_req_bytes'
            """
        ),
        {"svc": service, "mod": module},
    )
    compact_req, compact_resp = compact.one()

    return {
        "total_req_bytes": int(raw_req) + int(compact_req),
        "total_resp_bytes": int(raw_resp) + int(compact_resp),
    }


@router.get("/metrics/wom-rate-limit")
async def wom_rate_limit_metrics(
    minutes: int = Query(default=60, ge=5, le=1440),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Return WOM rate-limit snapshots from DB (last N minutes) merged with in-memory."""
    await require_staff(current_user, session)
    from app.services.http.wom_queue import get_wom_queue

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    db_rows = (
        (
            await session.execute(
                select(MetricRecord)
                .where(
                    MetricRecord.service_name == "api-backend",
                    MetricRecord.module_name == "wom_rate_limit",
                    MetricRecord.recorded_at >= cutoff,
                )
                .order_by(MetricRecord.recorded_at)
            )
        )
        .scalars()
        .all()
    )

    seen_ts: set[float] = set()
    result: list[dict] = []

    for row in db_rows:
        ts = row.recorded_at.timestamp()
        seen_ts.add(round(ts, 1))
        result.append(
            {
                "ts": ts,
                "remaining": row.metrics.get("remaining", 100),
                "reservedUsed": row.metrics.get("reserved_used", 0),
                "queueHigh": row.metrics.get("queue_high", 0),
                "queueNormal": row.metrics.get("queue_normal", 0),
                "queueLow": row.metrics.get("queue_low", 0),
            }
        )

    for s in get_wom_queue().snapshot_history():
        if round(s.ts, 1) not in seen_ts:
            result.append(
                {
                    "ts": s.ts,
                    "remaining": s.remaining,
                    "reservedUsed": s.reserved_used,
                    "queueHigh": s.queue_high,
                    "queueNormal": s.queue_normal,
                    "queueLow": s.queue_low,
                }
            )

    result.sort(key=lambda r: r["ts"])
    return result


@router.get("/metrics/history")
async def metrics_history(
    service: str = Query(...),
    module: str = Query(...),
    from_: datetime = Query(
        alias="from",
        default_factory=lambda: datetime.now(timezone.utc) - timedelta(days=7),
    ),
    to: datetime = Query(default_factory=lambda: datetime.now(timezone.utc)),
    limit: int = Query(default=2000, ge=1, le=2000),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return merged raw + compact metric history for a service/module pair."""
    await require_staff(current_user, session)

    raw_rows = await session.execute(
        select(MetricRecord)
        .where(
            MetricRecord.service_name == service,
            MetricRecord.module_name == module,
            MetricRecord.recorded_at >= from_,
            MetricRecord.recorded_at <= to,
        )
        .order_by(MetricRecord.recorded_at.desc())
        .limit(limit)
    )
    raw = [
        {
            "recorded_at": r.recorded_at.isoformat(),
            "metrics": r.metrics,
            "is_compact": False,
        }
        for r in raw_rows.scalars()
    ]

    compact_rows = await session.execute(
        select(MetricRecordCompact)
        .where(
            MetricRecordCompact.service_name == service,
            MetricRecordCompact.module_name == module,
            MetricRecordCompact.date >= from_.date(),
            MetricRecordCompact.date <= to.date(),
        )
        .order_by(MetricRecordCompact.date.desc())
    )
    compact = [
        {
            "recorded_at": r.date.isoformat(),
            "metrics": _flatten_compact_metrics(r.metrics_agg),
            "sample_count": r.sample_count,
            "is_compact": True,
        }
        for r in compact_rows.scalars()
    ]

    all_records = sorted(raw + compact, key=lambda r: r["recorded_at"], reverse=True)

    modules_result = await session.execute(
        text(
            "SELECT DISTINCT module_name FROM metric_records WHERE service_name = :svc"
            " UNION SELECT DISTINCT module_name FROM metric_records_compact WHERE service_name = :svc"
        ),
        {"svc": service},
    )
    modules = [row[0] for row in modules_result]

    return {"records": all_records, "modules": modules}
