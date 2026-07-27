from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.page_permissions import check_page_permission
from app.services.rank_mappings import get_effective_roles

_STALE_THRESHOLD_MINUTES = 10


class MetricReportBody(BaseModel):
    service_name: str
    module_name: str
    version: str | None = None
    uptime_seconds: int | None = None
    is_healthy: bool = True
    metrics: dict[str, Any] = {}


async def require_staff(current_user: dict[str, Any], session: AsyncSession) -> None:
    discord_user_id = int(current_user["sub"])
    roles = await get_effective_roles(discord_user_id, session)
    if not await check_page_permission("staff.home", "read", roles, session):
        raise HTTPException(status_code=403, detail="Permission denied.")


def api_backend_status(request: Request) -> dict[str, Any]:
    """Build live inline status for api-backend's own background services."""
    ranking_service = getattr(request.app.state, "ranking_service", None)
    valkey = getattr(request.app.state, "valkey", None)
    engine = getattr(request.app.state, "engine", None)

    ranking_metrics: dict[str, Any] = {}
    if ranking_service is not None:
        ranking_metrics = {
            "ranking_is_running": ranking_service.run_active,
            "ranking_last_run_at": ranking_service.last_run_at.isoformat()
            if ranking_service.last_run_at
            else None,
            "ranking_last_run_count": ranking_service.last_run_count,
            "ranking_last_error": ranking_service.last_error,
        }

    return {
        "service_name": "api-backend",
        "is_healthy": True,
        "last_seen": datetime.now(UTC).isoformat(),
        "version": None,
        "uptime_seconds": None,
        "summary_metrics": {
            "db_connected": engine is not None,
            "valkey_connected": valkey is not None,
            **ranking_metrics,
        },
    }
