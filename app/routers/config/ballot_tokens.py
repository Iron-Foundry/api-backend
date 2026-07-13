from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_session
from app.services.competition_schedule.ballot_tokens import DEFAULT_TOKEN_CONFIG
from app.services.page_permissions import require_page_permission

from ._helpers import _BALLOT_TOKEN_CONFIG_KEY, get_config_value, set_config_value

router = APIRouter()


class BallotTokenConfigBody(BaseModel):
    placement_tokens: list[int] = Field(min_length=0, max_length=5)
    bonus_threshold_pct: int = Field(ge=0, le=100)
    bonus_tokens: int = Field(ge=0)
    vote_cost: int = Field(ge=0)
    max_hold: int = Field(ge=0)


@router.get(
    "/ballot-tokens",
    dependencies=[Depends(require_page_permission("staff.ballot-tokens", "read"))],
)
async def get_ballot_token_config(
    session: AsyncSession = Depends(get_session),
) -> dict:
    stored = await get_config_value(_BALLOT_TOKEN_CONFIG_KEY, session)
    merged = dict(DEFAULT_TOKEN_CONFIG)
    merged.update({k: v for k, v in stored.items() if k in DEFAULT_TOKEN_CONFIG})
    return merged


@router.put(
    "/ballot-tokens",
    dependencies=[Depends(require_page_permission("staff.ballot-tokens", "edit"))],
)
async def set_ballot_token_config(
    body: BallotTokenConfigBody, session: AsyncSession = Depends(get_session)
) -> dict:
    value = body.model_dump()
    await set_config_value(_BALLOT_TOKEN_CONFIG_KEY, value, session)
    return value
