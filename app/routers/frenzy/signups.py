"""A member's own signup for a frenzy event."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FrenzyDraft, FrenzyEvent, FrenzySignup
from app.dependencies import get_current_user, get_session
from app.services.signup_account import signup_account

from .signup_schemas import FrenzySignupBody, FrenzySignupPatch, MyFrenzySignup

router = APIRouter()


async def _event_or_404(session: AsyncSession, event_id: int) -> FrenzyEvent:
    event = await session.get(FrenzyEvent, event_id)
    if event is None:
        raise HTTPException(404, "Event not found.")
    return event


async def find_signup(
    session: AsyncSession, event_id: int, user_id: int
) -> FrenzySignup | None:
    """The member's signup for the event, if they have one."""
    return (
        await session.execute(
            select(FrenzySignup).where(
                FrenzySignup.event_id == event_id,
                FrenzySignup.discord_user_id == user_id,
            )
        )
    ).scalar_one_or_none()


async def _own_signup_or_404(
    session: AsyncSession, event_id: int, user_id: int
) -> FrenzySignup:
    signup = await find_signup(session, event_id, user_id)
    if signup is None:
        raise HTTPException(404, "Signup not found.")
    return signup


async def _refuse_if_drafted(
    session: AsyncSession, event_id: int, signup: FrenzySignup
) -> None:
    """A signup stays fixed once the order is drawn, or while staff hold it as a captain."""
    draft = (
        await session.execute(
            select(FrenzyDraft).where(FrenzyDraft.event_id == event_id)
        )
    ).scalar_one_or_none()
    if draft and (draft.state != "setup" or signup.id in draft.captain_ids):
        raise HTTPException(409, "The draft holds this signup.")


@router.post("/events/{event_id}/signup", status_code=201)
async def sign_up(
    event_id: int,
    body: FrenzySignupBody = Body(default_factory=FrenzySignupBody),
    session: AsyncSession = Depends(get_session),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> MyFrenzySignup:
    """Sign the member up for the event under one of their linked RSNs."""
    event = await _event_or_404(session, event_id)
    if not event.signups_open:
        raise HTTPException(403, "Signups are closed.")
    user_id = int(current_user["sub"])
    if await find_signup(session, event_id, user_id) is not None:
        raise HTTPException(409, "Already signed up.")
    account = await signup_account(session, user_id, body.account_id)
    signup = FrenzySignup(
        event_id=event_id,
        discord_user_id=user_id,
        account_id=account.id,
        rsn=account.rsn,
        wants_captain=body.wants_captain,
        timezone=body.timezone,
        signed_up_at=datetime.now(UTC),
    )
    session.add(signup)
    await session.commit()
    return MyFrenzySignup.model_validate(signup, from_attributes=True)


@router.patch("/events/{event_id}/signup", status_code=204)
async def change_signup(
    event_id: int,
    body: FrenzySignupPatch,
    session: AsyncSession = Depends(get_session),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> Response:
    """Move the signup to another linked account, or change the opt-in or time zone."""
    user_id = int(current_user["sub"])
    signup = await _own_signup_or_404(session, event_id, user_id)
    await _refuse_if_drafted(session, event_id, signup)
    if body.account_id is not None:
        account = await signup_account(session, user_id, body.account_id)
        signup.account_id = account.id
        signup.rsn = account.rsn
    if body.wants_captain is not None:
        signup.wants_captain = body.wants_captain
    if body.timezone is not None:
        signup.timezone = body.timezone
    await session.commit()
    return Response(status_code=204)


@router.delete("/events/{event_id}/signup", status_code=204)
async def cancel_signup(
    event_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> Response:
    """Withdraw the member's signup from the event."""
    signup = await _own_signup_or_404(session, event_id, int(current_user["sub"]))
    await _refuse_if_drafted(session, event_id, signup)
    await session.delete(signup)
    await session.commit()
    return Response(status_code=204)
