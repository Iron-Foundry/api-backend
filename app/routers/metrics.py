"""Metrics router - service health reporting and time-series metric history."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MetricRecord, MetricRecordCompact, ServiceStatus
from app.dependencies import get_current_user, get_session, verify_metrics_key
from app.services.page_permissions import check_page_permission
from app.services.rank_mappings import get_effective_roles

router = APIRouter(tags=["metrics"])

_STALE_THRESHOLD_MINUTES = 10


class MetricReportBody(BaseModel):
    service_name: str
    module_name: str
    version: str | None = None
    uptime_seconds: int | None = None
    is_healthy: bool = True
    metrics: dict[str, Any] = {}


async def _require_staff(current_user: dict, session: AsyncSession) -> None:
    discord_user_id = int(current_user["sub"])
    roles = await get_effective_roles(discord_user_id, session)
    if not await check_page_permission("staff.home", "read", roles, session):
        raise HTTPException(status_code=403, detail="Permission denied.")


@router.post("/metrics/report")
async def report_metrics(
    body: MetricReportBody,
    _key: None = Depends(verify_metrics_key),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Upsert service status and append a time-series record."""
    now = datetime.now(timezone.utc)

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
    logger.debug(
        "metrics/report: {}/{} from service {}",
        body.service_name,
        body.module_name,
        body.service_name,
    )
    return {"ok": True}


@router.get("/services/status")
async def services_status(
    request: Request,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Return live service status for all reporting services plus api-backend itself."""
    await _require_staff(current_user, session)

    rows = await session.execute(select(ServiceStatus))
    services = list(rows.scalars())

    stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=_STALE_THRESHOLD_MINUTES)
    result: list[dict] = []
    for svc in services:
        is_healthy = svc.is_healthy and svc.last_seen > stale_cutoff
        result.append(
            {
                "service_name": svc.service_name,
                "is_healthy": is_healthy,
                "last_seen": svc.last_seen.isoformat(),
                "version": svc.version,
                "uptime_seconds": svc.uptime_seconds,
                "summary_metrics": svc.summary_metrics,
            }
        )

    live = _api_backend_status(request)
    existing = next((r for r in result if r["service_name"] == "api-backend"), None)
    if existing:
        existing["summary_metrics"] = {**existing["summary_metrics"], **live["summary_metrics"]}
        existing["is_healthy"] = live["is_healthy"]
        existing["last_seen"] = live["last_seen"]
    else:
        result.append(live)
    return result


def _api_backend_status(request: Request) -> dict:
    """Build live inline status for api-backend's own background services."""
    ranking_service = getattr(request.app.state, "ranking_service", None)
    valkey = getattr(request.app.state, "valkey", None)
    engine = getattr(request.app.state, "engine", None)

    ranking_metrics: dict[str, Any] = {}
    if ranking_service is not None:
        ranking_metrics = {
            "ranking_is_running": ranking_service.is_running,
            "ranking_last_run_at": ranking_service.last_run_at.isoformat()
            if ranking_service.last_run_at
            else None,
            "ranking_last_run_count": ranking_service.last_run_count,
            "ranking_last_error": ranking_service.last_error,
        }

    return {
        "service_name": "api-backend",
        "is_healthy": True,
        "last_seen": datetime.now(timezone.utc).isoformat(),
        "version": None,
        "uptime_seconds": None,
        "summary_metrics": {
            "db_connected": engine is not None,
            "valkey_connected": valkey is not None,
            **ranking_metrics,
        },
    }


@router.get("/services/uptime")
async def services_uptime(
    days: int = Query(default=90, ge=7, le=365),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Return per-day operational status for all services over the last N days."""
    await _require_staff(current_user, session)

    active_rows = await session.execute(
        text(
            """
            SELECT service_name, (recorded_at AT TIME ZONE 'UTC')::date AS day
            FROM metric_records
            WHERE recorded_at >= CURRENT_DATE - :days * interval '1 day'
            GROUP BY service_name, day
            UNION
            SELECT service_name, date AS day
            FROM metric_records_compact
            WHERE date >= CURRENT_DATE - :days
            GROUP BY service_name, date
            """
        ),
        {"days": days},
    )
    active: dict[str, set[str]] = {}
    for service_name, day in active_rows:
        active.setdefault(service_name, set()).add(str(day))

    first_seen_rows = await session.execute(
        text(
            """
            SELECT service_name, MIN(day) FROM (
                SELECT service_name, (recorded_at AT TIME ZONE 'UTC')::date AS day
                FROM metric_records
                UNION ALL
                SELECT service_name, date AS day
                FROM metric_records_compact
            ) t GROUP BY service_name
            """
        )
    )
    first_seen: dict[str, str] = {sn: str(d) for sn, d in first_seen_rows}

    today = datetime.now(timezone.utc).date()
    window_start = today - timedelta(days=days - 1)
    all_dates = [str(window_start + timedelta(days=i)) for i in range(days)]

    all_services_rows = await session.execute(select(ServiceStatus.service_name))
    all_services = {row[0] for row in all_services_rows}
    all_services.update(active.keys())
    all_services.add("api-backend")

    result: list[dict] = []
    for service_name in sorted(all_services):
        service_active = active.get(service_name, set())
        fs = first_seen.get(service_name)
        reporting_start = max(window_start, datetime.strptime(fs, "%Y-%m-%d").date()) if fs else None

        day_list: list[dict] = []
        operational_count = 0
        total_count = 0

        for date_str in all_dates:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
            if reporting_start is None or date_obj < reporting_start:
                day_list.append({"date": date_str, "status": "no_data"})
            elif date_str in service_active:
                day_list.append({"date": date_str, "status": "operational"})
                operational_count += 1
                total_count += 1
            else:
                day_list.append({"date": date_str, "status": "incident"})
                total_count += 1

        uptime_pct = round((operational_count / total_count * 100), 2) if total_count > 0 else None

        result.append(
            {
                "service_name": service_name,
                "uptime_pct": uptime_pct,
                "days": day_list,
            }
        )

    return result


@router.get("/metrics/bandwidth")
async def metrics_bandwidth(
    service: str = Query(default="api-backend"),
    module: str = Query(default="endpoints"),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return all-time total request and response bytes for a service/module pair."""
    await _require_staff(current_user, session)

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


@router.get("/metrics/history")
async def metrics_history(
    service: str = Query(...),
    module: str = Query(...),
    from_: datetime = Query(
        alias="from",
        default_factory=lambda: datetime.now(timezone.utc) - timedelta(days=7),
    ),
    to: datetime = Query(
        default_factory=lambda: datetime.now(timezone.utc),
    ),
    limit: int = Query(default=500, ge=1, le=2000),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return merged raw + compact metric history for a service/module pair."""
    await _require_staff(current_user, session)

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
        .limit(limit)
    )
    compact = [
        {
            "recorded_at": r.date.isoformat(),
            "metrics": r.metrics_agg,
            "sample_count": r.sample_count,
            "is_compact": True,
        }
        for r in compact_rows.scalars()
    ]

    all_records = sorted(
        raw + compact, key=lambda r: r["recorded_at"], reverse=True
    )[:limit]

    modules_result = await session.execute(
        text(
            "SELECT DISTINCT module_name FROM metric_records WHERE service_name = :svc"
            " UNION SELECT DISTINCT module_name FROM metric_records_compact WHERE service_name = :svc"
        ),
        {"svc": service},
    )
    modules = [row[0] for row in modules_result]

    return {"records": all_records, "modules": modules}
