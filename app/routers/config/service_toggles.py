from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_session
from app.services.page_permissions import require_page_permission
from app.services.toggle_dispatch import TOGGLE_CHANNEL

from ._helpers import (
    _ALL_SERVICE_KEYS,
    _SERVICE_TOGGLES_KEY,
    get_service_toggles,
    set_config_value,
)

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
    """Return which background services are enabled."""
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
    """Enable or disable a background service. Persists to DB and applies at runtime.

    Published rather than applied in place: gunicorn runs several workers, each
    holding its own service registry, so a toggle applied here would reach one
    of them. `ToggleDispatchService` in every worker - including this one - acts
    on the publish.
    """
    if service_key not in _ALL_SERVICE_KEYS:
        raise HTTPException(
            status_code=404, detail=f"Unknown service key: {service_key}"
        )
    current = await get_service_toggles(session)
    current[service_key] = body.enabled
    await set_config_value(_SERVICE_TOGGLES_KEY, current, session)
    await request.app.state.valkey.publish(
        TOGGLE_CHANNEL,
        json.dumps({"service_key": service_key, "enabled": body.enabled}),
    )
    return current
