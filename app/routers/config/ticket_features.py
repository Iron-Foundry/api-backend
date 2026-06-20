from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_session
from app.services.page_permissions import require_page_permission

from ._helpers import _TICKET_FEATURES_KEY, get_config_value, set_config_value

router = APIRouter()


class TicketFeaturesConfig(BaseModel):
    rank_pull_set_primary: bool = False


@router.get(
    "/ticket-features",
    dependencies=[Depends(require_page_permission("staff.ticket-config", "read"))],
)
async def get_ticket_features(
    session: AsyncSession = Depends(get_session),
) -> TicketFeaturesConfig:
    data = await get_config_value(_TICKET_FEATURES_KEY, session)
    return TicketFeaturesConfig(
        rank_pull_set_primary=bool(data.get("rank_pull_set_primary", False))
    )


@router.put(
    "/ticket-features",
    dependencies=[Depends(require_page_permission("staff.ticket-config", "edit"))],
)
async def set_ticket_features(
    body: TicketFeaturesConfig, session: AsyncSession = Depends(get_session)
) -> TicketFeaturesConfig:
    await set_config_value(_TICKET_FEATURES_KEY, body.model_dump(), session)
    return body
