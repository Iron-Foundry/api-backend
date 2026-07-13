from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PlayerRanking, TileRaceEvent, TileRaceSignup, UserAccount
from app.dependencies import get_current_user, get_session

from .schemas import SignupBody, SignupPatch

router = APIRouter()


async def _resolve_account(
    session: AsyncSession, user_id: int, account_id: int | None
) -> UserAccount:
    stmt = select(UserAccount).where(UserAccount.discord_user_id == user_id)
    if account_id is not None:
        stmt = stmt.where(UserAccount.id == account_id)
    else:
        stmt = stmt.order_by(
            UserAccount.is_primary.desc(), UserAccount.created_at.asc()
        )
    account = (await session.execute(stmt.limit(1))).scalars().first()
    if account is None:
        raise HTTPException(422, "No linked account to sign up with.")
    return account


async def _ranking_score(session: AsyncSession, rsn: str) -> int:
    ranking = (
        (
            await session.execute(
                select(PlayerRanking)
                .where(func.lower(PlayerRanking.rsn) == rsn.lower())
                .order_by(PlayerRanking.points.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    return ranking.points if ranking else 0


async def _get_signup(
    session: AsyncSession, event_id: int, user_id: int
) -> TileRaceSignup | None:
    return (
        await session.execute(
            select(TileRaceSignup).where(
                TileRaceSignup.event_id == event_id,
                TileRaceSignup.discord_user_id == user_id,
            )
        )
    ).scalar_one_or_none()


@router.post("/events/{event_id}/signup", status_code=201)
async def sign_up(
    event_id: int,
    body: SignupBody = SignupBody(),
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    event = (
        await session.execute(select(TileRaceEvent).where(TileRaceEvent.id == event_id))
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found.")
    if not event.signups_open:
        raise HTTPException(403, "Signups are closed.")
    user_id = int(current_user["sub"])
    if await _get_signup(session, event_id, user_id) is not None:
        raise HTTPException(409, "Already signed up.")
    account = await _resolve_account(session, user_id, body.account_id)
    session.add(
        TileRaceSignup(
            event_id=event_id,
            discord_user_id=user_id,
            account_id=account.id,
            rsn=account.rsn,
            ranking_score=await _ranking_score(session, account.rsn),
            wants_captain=body.wants_captain,
            signed_up_at=datetime.now(timezone.utc),
        )
    )
    await session.commit()
    return {"ok": True}


@router.patch("/events/{event_id}/signup")
async def change_signup(
    event_id: int,
    body: SignupPatch,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    user_id = int(current_user["sub"])
    signup = await _get_signup(session, event_id, user_id)
    if signup is None:
        raise HTTPException(404, "Signup not found.")
    if body.account_id is not None:
        account = await _resolve_account(session, user_id, body.account_id)
        signup.account_id = account.id
        signup.rsn = account.rsn
        signup.ranking_score = await _ranking_score(session, account.rsn)
    if body.wants_captain is not None:
        signup.wants_captain = body.wants_captain
    await session.commit()
    return {"ok": True}


@router.delete("/events/{event_id}/signup")
async def cancel_signup(
    event_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    user_id = int(current_user["sub"])
    signup = await _get_signup(session, event_id, user_id)
    if signup is None:
        raise HTTPException(404, "Signup not found.")
    await session.delete(signup)
    await session.commit()
    return {"ok": True}
