from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PlayerRanking, User, UserAccount
from app.dependencies import get_current_user, get_session
from app.services.rsn_cascade import backfill_user_from_rsn

from ._helpers import _ACCOUNT_CAP, _CAP_MSG, _RSN_RE, AddAccount, _wom_link_rsn

router = APIRouter()


@router.get("/me/accounts")
async def list_accounts(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    discord_user_id = int(current_user["sub"])
    result = await session.execute(
        select(UserAccount)
        .where(UserAccount.discord_user_id == discord_user_id)
        .order_by(UserAccount.is_primary.desc(), UserAccount.created_at.asc())
    )
    return [
        {"id": row.id, "rsn": row.rsn, "is_primary": row.is_primary, "created_at": row.created_at.isoformat()}
        for row in result.scalars()
    ]


@router.get("/me/rankings")
async def get_me_rankings(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    discord_user_id = int(current_user["sub"])
    result = await session.execute(
        select(UserAccount.rsn, UserAccount.is_primary, PlayerRanking.rank, PlayerRanking.points, PlayerRanking.boss_points, PlayerRanking.skill_points)
        .outerjoin(PlayerRanking, func.lower(PlayerRanking.rsn) == func.lower(UserAccount.rsn))
        .where(UserAccount.discord_user_id == discord_user_id)
        .order_by(UserAccount.is_primary.desc(), UserAccount.created_at.asc())
    )
    return [
        {"rsn": row.rsn, "is_primary": row.is_primary, "rank": row.rank, "points": row.points, "boss_points": row.boss_points, "skill_points": row.skill_points}
        for row in result.all()
    ]


@router.post("/me/accounts", status_code=201)
async def add_account(
    body: AddAccount,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
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
        select(UserAccount.discord_user_id).where(func.lower(UserAccount.rsn) == rsn.lower())
    )
    conflict_owner = conflict_result.scalar_one_or_none()
    if conflict_owner == discord_user_id:
        raise HTTPException(status_code=409, detail="That RSN is already linked to your account.")
    if conflict_owner is not None:
        raise HTTPException(status_code=409, detail="That RSN is linked to another account.")

    cap_result = await session.execute(
        select(func.count()).select_from(UserAccount).where(UserAccount.discord_user_id == discord_user_id)
    )
    current_count = cap_result.scalar_one() or 0
    if current_count >= _ACCOUNT_CAP:
        raise HTTPException(status_code=422, detail=_CAP_MSG)

    now = datetime.now(timezone.utc)
    is_first = current_count == 0
    new_row = UserAccount(discord_user_id=discord_user_id, rsn=rsn, is_primary=is_first, created_at=now)
    session.add(new_row)
    await session.flush()

    if is_first:
        await session.execute(
            update(User).where(User.discord_user_id == discord_user_id).values(rsn=rsn, updated_at=now)
        )

    user_result = await session.execute(
        select(User.clan_rank, User.total_loot_value, User.collection_log_slots).where(User.discord_user_id == discord_user_id)
    )
    user_row = user_result.one_or_none()
    await backfill_user_from_rsn(
        session, discord_user_id, rsn,
        clan_rank=user_row.clan_rank if user_row else None,
        total_loot_value=user_row.total_loot_value if user_row else 0,
        collection_log_slots=user_row.collection_log_slots if user_row else 0,
    )

    await _wom_link_rsn(session, discord_user_id, rsn, new_row.id)
    await session.commit()
    logger.info("members/accounts: user {} added RSN {!r}", discord_user_id, rsn)
    return {"id": new_row.id, "rsn": new_row.rsn, "is_primary": new_row.is_primary, "created_at": new_row.created_at.isoformat()}


@router.patch("/me/accounts/{account_id}/set-primary")
async def set_primary_account(
    account_id: int,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    discord_user_id = int(current_user["sub"])
    row_result = await session.execute(
        select(UserAccount).where(UserAccount.id == account_id, UserAccount.discord_user_id == discord_user_id)
    )
    row = row_result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Account not found.")
    if row.is_primary:
        return {"id": row.id, "rsn": row.rsn, "is_primary": True}
    now = datetime.now(timezone.utc)
    await session.execute(
        update(UserAccount)
        .where(UserAccount.discord_user_id == discord_user_id, UserAccount.is_primary == True)  # noqa: E712
        .values(is_primary=False)
    )
    await session.execute(update(UserAccount).where(UserAccount.id == account_id).values(is_primary=True))
    await session.execute(update(User).where(User.discord_user_id == discord_user_id).values(rsn=row.rsn, updated_at=now))
    await session.commit()
    logger.info("members/accounts: user {} set primary {!r}", discord_user_id, row.rsn)
    return {"id": row.id, "rsn": row.rsn, "is_primary": True}


@router.delete("/me/accounts/{account_id}", status_code=204)
async def delete_account(
    account_id: int,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    discord_user_id = int(current_user["sub"])
    row_result = await session.execute(
        select(UserAccount).where(UserAccount.id == account_id, UserAccount.discord_user_id == discord_user_id)
    )
    row = row_result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Account not found.")
    count_result = await session.execute(
        select(func.count()).select_from(UserAccount).where(UserAccount.discord_user_id == discord_user_id)
    )
    total = count_result.scalar_one() or 0
    if row.is_primary and total > 1:
        raise HTTPException(
            status_code=422,
            detail="Cannot delete primary account while other accounts are linked. Set a different primary first.",
        )
    now = datetime.now(timezone.utc)
    if total == 1:
        await session.execute(update(User).where(User.discord_user_id == discord_user_id).values(rsn=None, updated_at=now))
    await session.delete(row)
    await session.commit()
    logger.info("members/accounts: user {} removed RSN {!r}", discord_user_id, row.rsn)
