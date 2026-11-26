"""The linked account an event signup uses: the one asked for, else the primary."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UserAccount


async def signup_account(
    session: AsyncSession, user_id: int, account_id: int | None
) -> UserAccount:
    """The member's account with `account_id`, or their primary when it is None.

    Raises 422 when the member has no such linked account.
    """
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
