from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, UserAccount
from app.dependencies import get_current_user, get_session
from app.services.rsn_cascade import backfill_user_from_rsn

from ._helpers import (
    _ACCOUNT_CAP,
    _CAP_MSG,
    _RSN_RE,
    RsnUpdate,
    _upsert_primary_account,
    _wom_link_rsn,
)

router = APIRouter()


@router.patch("/me/rsn")
async def update_rsn(
    body: RsnUpdate,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    rsn = body.rsn.strip()
    if not rsn:
        raise HTTPException(status_code=422, detail="RSN cannot be empty.")
    if not _RSN_RE.match(rsn):
        raise HTTPException(
            status_code=422,
            detail="RSN must be 1-12 characters: letters, numbers, spaces, hyphens, underscores.",
        )
    discord_user_id = int(current_user["sub"])

    conflict_result = await session.execute(
        select(UserAccount.discord_user_id).where(
            func.lower(UserAccount.rsn) == rsn.lower()
        )
    )
    conflict = conflict_result.scalar_one_or_none()
    if conflict and conflict != discord_user_id:
        raise HTTPException(
            status_code=409, detail="That RSN is linked to another account."
        )

    if not conflict:
        cap_result = await session.execute(
            select(func.count())
            .select_from(UserAccount)
            .where(UserAccount.discord_user_id == discord_user_id)
        )
        if (cap_result.scalar_one() or 0) >= _ACCOUNT_CAP:
            raise HTTPException(status_code=422, detail=_CAP_MSG)

    await _upsert_primary_account(session, discord_user_id, rsn)
    logger.info("members/rsn: user {} set primary RSN {!r}", discord_user_id, rsn)

    user_result = await session.execute(
        select(User.clan_rank, User.total_loot_value, User.collection_log_slots).where(
            User.discord_user_id == discord_user_id
        )
    )
    user_row = user_result.one_or_none()
    backfill = await backfill_user_from_rsn(
        session,
        discord_user_id,
        rsn,
        clan_rank=user_row.clan_rank if user_row else None,
        total_loot_value=user_row.total_loot_value if user_row else 0,
        collection_log_slots=user_row.collection_log_slots if user_row else 0,
    )
    if backfill:
        logger.info(
            "members/rsn: backfilled fields {} for user {}",
            list(backfill.keys()),
            discord_user_id,
        )

    ua_result = await session.execute(
        select(UserAccount.id).where(
            UserAccount.discord_user_id == discord_user_id,
            func.lower(UserAccount.rsn) == rsn.lower(),
        )
    )
    ua_id = ua_result.scalar_one_or_none()
    await _wom_link_rsn(session, discord_user_id, rsn, ua_id)
    await session.commit()
    return {"rsn": rsn}
