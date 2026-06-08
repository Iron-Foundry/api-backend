from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_session
from app.services.page_permissions import require_page_permission

from ._helpers import _ALL_SERVICE_KEYS, _SERVICE_TOGGLES_KEY, get_service_toggles, set_config_value

router = APIRouter()


class ServiceToggleBody(BaseModel):
    enabled: bool


@router.get(
    "/services/toggles",
    dependencies=[Depends(require_page_permission("staff.services", "read"))],
)
async def get_service_toggles_endpoint(
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    return await get_service_toggles(session)


@router.put(
    "/services/toggles/{service_key}",
    dependencies=[Depends(require_page_permission("staff.services", "edit"))],
)
async def set_service_toggle(
    service_key: str,
    body: ServiceToggleBody,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    """Enable or disable a background service. Persists to DB and applies at runtime."""
    if service_key not in _ALL_SERVICE_KEYS:
        raise HTTPException(status_code=404, detail=f"Unknown service key: {service_key}")
    current = await get_service_toggles(session)
    current[service_key] = body.enabled
    await set_config_value(_SERVICE_TOGGLES_KEY, current, session)
    registry: dict[str, Any] = getattr(request.app.state, "service_registry", {})
    svc = registry.get(service_key)
    if svc is not None:
        if body.enabled and not svc.is_running:
            await svc.start()
        elif not body.enabled and svc.is_running:
            await svc.stop()
    else:
        logger.warning("Service {} not in registry (may require WOM_GROUP_ID)", service_key)
    return current
