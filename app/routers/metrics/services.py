from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ServiceStatus
from app.dependencies import get_current_user, get_session

from ._helpers import _STALE_THRESHOLD_MINUTES, api_backend_status, require_staff

router = APIRouter()


@router.get("/services/status")
async def services_status(
    request: Request,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Return live service status for all reporting services plus api-backend itself."""
    await require_staff(current_user, session)

    rows = await session.execute(select(ServiceStatus))
    services = list(rows.scalars())

    stale_cutoff = datetime.now(timezone.utc) - timedelta(
        minutes=_STALE_THRESHOLD_MINUTES
    )
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

    live = api_backend_status(request)
    existing = next((r for r in result if r["service_name"] == "api-backend"), None)
    if existing:
        existing["summary_metrics"] = {
            **existing["summary_metrics"],
            **live["summary_metrics"],
        }
        existing["is_healthy"] = live["is_healthy"]
        existing["last_seen"] = live["last_seen"]
    else:
        result.append(live)
    return result


@router.get("/services/uptime")
async def services_uptime(
    days: int = Query(default=90, ge=7, le=365),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Return per-day operational status for all services over the last N days."""
    await require_staff(current_user, session)

    active_rows = await session.execute(
        text(
            """
            SELECT service_name, (recorded_at AT TIME ZONE 'UTC')::date AS day
            FROM metric_records
            WHERE recorded_at >= CURRENT_DATE - CAST(:days AS INTEGER) * interval '1 day'
            GROUP BY service_name, day
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
            SELECT service_name, MIN((recorded_at AT TIME ZONE 'UTC')::date)
            FROM metric_records
            GROUP BY service_name
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
        reporting_start = (
            max(window_start, datetime.strptime(fs, "%Y-%m-%d").date()) if fs else None
        )

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

        uptime_pct = (
            round((operational_count / total_count * 100), 2)
            if total_count > 0
            else None
        )
        result.append(
            {"service_name": service_name, "uptime_pct": uptime_pct, "days": day_list}
        )

    return result
