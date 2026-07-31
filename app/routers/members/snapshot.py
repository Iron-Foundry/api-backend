from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PlayerSnapshot, UserAccount
from app.dependencies import get_current_user, get_session

router = APIRouter()


def _empty_snapshot(rsn: str | None) -> dict[str, Any]:
    return {
        "rsn": rsn,
        "skills": {},
        "bosses": {},
        "activities": {},
        "ehp": None,
        "ehb": None,
        "fetched_at": None,
    }


@router.get("/me/snapshot")
async def get_me_snapshot(
    rsn: str | None = Query(None),
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return the latest WOM skill/boss/activity snapshot for one of the user's linked RSNs."""
    discord_user_id = int(current_user["sub"])

    if rsn:
        owned = await session.execute(
            select(UserAccount.rsn).where(
                UserAccount.discord_user_id == discord_user_id,
                func.lower(UserAccount.rsn) == rsn.lower(),
            )
        )
        if not owned.scalar_one_or_none():
            raise HTTPException(
                status_code=403, detail="RSN not linked to your account"
            )
    else:
        rsn_result = await session.execute(
            select(UserAccount.rsn).where(
                UserAccount.discord_user_id == discord_user_id,
                UserAccount.is_primary.is_(True),
            )
        )
        rsn = rsn_result.scalar_one_or_none()

    if not rsn:
        return _empty_snapshot(None)

    snap_result = await session.execute(
        select(
            PlayerSnapshot.skills,
            PlayerSnapshot.bosses,
            PlayerSnapshot.activities,
            PlayerSnapshot.ehp,
            PlayerSnapshot.ehb,
            PlayerSnapshot.fetched_at,
        ).where(func.lower(PlayerSnapshot.rsn) == rsn.lower())
    )
    row = snap_result.one_or_none()
    if not row:
        return _empty_snapshot(rsn)

    return {
        "rsn": rsn,
        "skills": row.skills or {},
        "bosses": row.bosses or {},
        "activities": row.activities or {},
        "ehp": row.ehp,
        "ehb": row.ehb,
        "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
    }
