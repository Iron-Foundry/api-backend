from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_session
from app.services.page_permissions import require_page_permission
from app.services.ranking_service import _DEFAULT_CONFIG

from ._helpers import _RANKING_CONFIG_KEY, get_config_value, set_config_value

router = APIRouter()


@router.get(
    "/ranking",
    dependencies=[Depends(require_page_permission("staff.ranking", "read"))],
)
async def get_ranking_config(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return the point weights and thresholds the rank engine uses."""
    data = await get_config_value(_RANKING_CONFIG_KEY, session)
    if not data or data.get("version") != 2:
        return _DEFAULT_CONFIG.to_dict()
    return data


@router.put(
    "/ranking",
    dependencies=[Depends(require_page_permission("staff.ranking", "edit"))],
)
async def set_ranking_config(
    body: dict[str, Any], session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """Replace the rank engine's point weights and thresholds."""
    await set_config_value(_RANKING_CONFIG_KEY, body, session)
    return body
