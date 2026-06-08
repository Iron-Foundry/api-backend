from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import cast

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Event, User, UserAccount
from app.dependencies import get_current_user, get_session
from app.services.rsn_cascade import backfill_event_user_account, backfill_user_from_rsn, cascade_rsn_change

from ._helpers import require_rank

router = APIRouter()

_RSN_RE = re.compile(r"^[A-Za-z0-9 _-]{1,12}$")


class StaffRsnUpdate(BaseModel):
    rsn: str | None


class StaffCascadeBody(BaseModel):
    old_rsn: str | None = None


@router.patch("/members/{user_id}/rsn")
async def update_member_rsn(
    user_id: int,
    body: StaffRsnUpdate,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Set, change, or clear a member's RSN. Performs backfill and event-linking."""
    await require_rank("staff.members", "edit", current_user, session)

    new_rsn = body.rsn.strip() if body.rsn else None
    if new_rsn == "":
        new_rsn = None

    if new_rsn and not _RSN_RE.match(new_rsn):
        raise HTTPException(422, "RSN must be 1-12 characters: letters, numbers, spaces, hyphens, underscores.")

    user_result = await session.execute(
        select(User.discord_user_id, User.rsn, User.clan_rank, User.total_loot_value, User.collection_log_slots)
        .where(User.discord_user_id == user_id)
    )
    user_row = user_result.one_or_none()
    if not user_row:
        raise HTTPException(404, "Member not found.")

    old_rsn: str | None = user_row.rsn
    now = datetime.now(timezone.utc)

    if new_rsn is None:
        await session.execute(update(User).where(User.discord_user_id == user_id).values(rsn=None, updated_at=now))
        if old_rsn:
            await session.execute(
                update(Event)
                .where(Event.user_id == user_id, func.lower(Event.player_name) == old_rsn.lower())
                .values(user_id=None)
            )
        await session.commit()
        logger.info("staff/rsn: cleared RSN for user {}", user_id)
        return {"discord_user_id": str(user_id), "rsn": None}

    conflict = await session.execute(
        select(User.discord_user_id).where(
            func.lower(User.rsn) == new_rsn.lower(), User.discord_user_id != user_id
        )
    )
    if conflict.scalar_one_or_none():
        raise HTTPException(409, "RSN already linked to another account.")

    if old_rsn and old_rsn.lower() != new_rsn.lower():
        await cascade_rsn_change(session, old_rsn, new_rsn)
        logger.info("staff/rsn: cascaded rename {!r} -> {!r} for user {}", old_rsn, new_rsn, user_id)

    await session.execute(update(User).where(User.discord_user_id == user_id).values(rsn=new_rsn, updated_at=now))
    logger.info("staff/rsn: user {} set RSN {!r}", user_id, new_rsn)

    backfill = await backfill_user_from_rsn(
        session, user_id, new_rsn,
        clan_rank=user_row.clan_rank,
        total_loot_value=user_row.total_loot_value or 0,
        collection_log_slots=user_row.collection_log_slots or 0,
    )
    if backfill:
        logger.info("staff/rsn: backfilled {} for user {}", list(backfill.keys()), user_id)

    ua_result = await session.execute(
        select(UserAccount.id, UserAccount.rsn_history).where(
            UserAccount.discord_user_id == user_id,
            func.lower(UserAccount.rsn) == new_rsn.lower(),
        )
    )
    ua_row = ua_result.one_or_none()
    ua_id = ua_row.id if ua_row else None
    all_rsns = [new_rsn] + (ua_row.rsn_history if ua_row else [])

    event_result = await session.execute(
        update(Event)
        .where(func.lower(Event.player_name) == new_rsn.lower())
        .values(user_id=user_id, **({"user_account_id": ua_id} if ua_id else {}))
    )
    if ua_id:
        await backfill_event_user_account(session, ua_id, all_rsns)
    logger.info("staff/rsn: linked user_id {} to {} event rows (ua_id={})", user_id, cast(CursorResult, event_result).rowcount, ua_id)

    await session.commit()
    return {"discord_user_id": user_id, "rsn": new_rsn}


@router.post("/members/{user_id}/rsn/cascade")
async def force_rsn_cascade(
    user_id: int,
    body: StaffCascadeBody = StaffCascadeBody(),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Force a full RSN cascade. Supply old_rsn to cascade a name predating user_accounts."""
    await require_rank("staff.members", "edit", current_user, session)

    user_result = await session.execute(select(User.rsn).where(User.discord_user_id == user_id))
    user_row = user_result.one_or_none()
    if not user_row:
        raise HTTPException(404, "Member not found.")

    current_rsn: str | None = user_row.rsn
    if not current_rsn:
        raise HTTPException(400, "Member has no RSN set.")

    old_rsn = body.old_rsn.strip() if body.old_rsn else current_rsn
    if old_rsn and not _RSN_RE.match(old_rsn):
        raise HTTPException(422, "old_rsn must be 1-12 characters: letters, numbers, spaces, hyphens, underscores.")

    await cascade_rsn_change(session, old_rsn, current_rsn)
    logger.info("staff/rsn: force cascade for user {} ({!r} -> {!r})", user_id, old_rsn, current_rsn)

    return {"discord_user_id": str(user_id), "rsn": current_rsn, "from_rsn": old_rsn}
