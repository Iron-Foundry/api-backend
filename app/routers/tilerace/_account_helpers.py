"""Repointing a roster entry at another of the member's linked accounts."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TileRaceSignup, UserAccount

from ._roster_helpers import ranking_score
from .schemas import RosterPatch


async def linked_accounts(
    session: AsyncSession, discord_user_id: int
) -> list[UserAccount]:
    """Every RSN linked to the member, primary first, for the switcher."""
    rows = await session.execute(
        select(UserAccount)
        .where(UserAccount.discord_user_id == discord_user_id)
        .order_by(UserAccount.is_primary.desc(), UserAccount.created_at.asc())
    )
    return list(rows.scalars().all())


async def account_or_422(
    session: AsyncSession, discord_user_id: int, account_id: int
) -> UserAccount:
    account = (
        await session.execute(
            select(UserAccount).where(
                UserAccount.id == account_id,
                UserAccount.discord_user_id == discord_user_id,
            )
        )
    ).scalar_one_or_none()
    if account is None:
        raise HTTPException(422, "That account is not linked to this member.")
    return account


async def apply_identity(
    session: AsyncSession, entry: TileRaceSignup, body: RosterPatch
) -> None:
    """Switch which RSN the entry races under, mid-event if need be.

    A signup made against the wrong account is usually only noticed once the
    teams are out, so this moves the RSN and the ranking score the draft read
    without touching the team assignment or the captain badge.
    """
    if "account_id" in body.model_fields_set and body.account_id is not None:
        account = await account_or_422(session, entry.discord_user_id, body.account_id)
        entry.account_id = account.id
        await _set_rsn(session, entry, account.rsn)
    elif body.rsn is not None:
        entry.account_id = None
        await _set_rsn(session, entry, body.rsn)


async def _set_rsn(session: AsyncSession, entry: TileRaceSignup, rsn: str) -> None:
    entry.rsn = rsn
    entry.ranking_score = await ranking_score(session, rsn)
