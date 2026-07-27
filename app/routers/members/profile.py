from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PlayerRanking, User
from app.dependencies import get_current_user, get_optional_user, get_session

from ._helpers import _REFERRAL_SOURCES, PrivacyUpdate, ReferralUpdate

router = APIRouter()


@router.patch("/me/privacy")
async def update_privacy(
    body: PrivacyUpdate,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    discord_user_id = int(current_user["sub"])
    values: dict[str, Any] = {"updated_at": datetime.now(UTC)}
    if body.stats_opt_out is not None:
        values["stats_opt_out"] = body.stats_opt_out
    if body.hide_presence_notifications is not None:
        values["hide_presence_notifications"] = body.hide_presence_notifications
    if len(values) == 1:
        return {}
    await session.execute(
        update(User).where(User.discord_user_id == discord_user_id).values(**values)
    )
    await session.commit()
    logger.info("members/privacy: user {} updated privacy {}", discord_user_id, values)
    return {k: v for k, v in values.items() if k != "updated_at"}


@router.get("/me/stats")
async def get_me_stats(
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    discord_user_id = int(current_user["sub"])
    user_result = await session.execute(
        select(
            User.collection_log_slots,
            User.collection_log_slots_max,
            User.total_loot_value,
            User.rsn,
        ).where(User.discord_user_id == discord_user_id)
    )
    user_row = user_result.one_or_none()
    rank_tier: str | None = None
    if user_row and user_row.rsn:
        ranking_result = await session.execute(
            select(PlayerRanking.rank).where(PlayerRanking.rsn.ilike(user_row.rsn))
        )
        rank_tier = ranking_result.scalar_one_or_none()
    return {
        "collection_log_slots": user_row.collection_log_slots if user_row else 0,
        "collection_log_slots_max": user_row.collection_log_slots_max
        if user_row
        else 0,
        "total_loot_value": user_row.total_loot_value if user_row else 0,
        "rank_tier": rank_tier,
    }


@router.patch("/me/referral")
async def update_referral(
    body: ReferralUpdate,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if body.source not in _REFERRAL_SOURCES:
        raise HTTPException(status_code=422, detail="Invalid referral source.")
    detail = body.detail.strip() if body.detail else None
    if body.source == "recruited_by" and not detail:
        raise HTTPException(status_code=422, detail="Recruiter name required.")
    if body.source == "other" and not detail:
        raise HTTPException(status_code=422, detail="Please describe how you found us.")
    discord_user_id = int(current_user["sub"])
    now = datetime.now(UTC)
    await session.execute(
        update(User)
        .where(User.discord_user_id == discord_user_id, User.referral_source.is_(None))
        .values(referral_source=body.source, referral_detail=detail, updated_at=now)
    )
    await session.commit()
    logger.info("members/referral: user {} source={!r}", discord_user_id, body.source)
    return {"ok": True}


@router.get("/{user_id}/avatar")
async def user_avatar(
    user_id: int,
    _current_user: dict[str, Any] | None = Depends(get_optional_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return the stored Discord avatar URL for the given user ID."""
    result = await session.execute(
        select(User.discord_avatar_url).where(User.discord_user_id == user_id)
    )
    avatar_url = result.scalar_one_or_none()
    if not avatar_url:
        raise HTTPException(status_code=404, detail="Avatar not available.")
    return {"avatar_url": avatar_url}
