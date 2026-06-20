from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_session
from app.services.page_permissions import require_page_permission

from ._helpers import _PANEL_CONFIG_KEY, get_config_value, set_config_value
from ._panel_models import InfoPanelConfig

router = APIRouter()


@router.get(
    "/panel",
    dependencies=[Depends(require_page_permission("staff.panel", "read"))],
)
async def get_panel_config(
    session: AsyncSession = Depends(get_session),
) -> InfoPanelConfig:
    data = await get_config_value(_PANEL_CONFIG_KEY, session)
    if not data:
        return InfoPanelConfig()
    return InfoPanelConfig.model_validate(data)


@router.put(
    "/panel",
    dependencies=[Depends(require_page_permission("staff.panel", "edit"))],
)
async def set_panel_config(
    body: InfoPanelConfig, session: AsyncSession = Depends(get_session)
) -> InfoPanelConfig:
    await set_config_value(_PANEL_CONFIG_KEY, body.model_dump(), session)
    return body
