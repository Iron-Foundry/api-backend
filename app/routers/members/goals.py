from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MemberGoals, UserAccount
from app.dependencies import get_current_user, get_session

router = APIRouter()


class GoalsSaveRequest(BaseModel):
    goals: list[dict[str, Any]]


@router.get("/goals/{token}")
async def get_goals_by_token(
    token: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return stored goals for a share token (public)."""
    result = await session.execute(
        select(MemberGoals.rsn, MemberGoals.goals, MemberGoals.updated_at).where(
            MemberGoals.share_token == token
        )
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Goals not found")
    return {
        "rsn": row.rsn,
        "goals": row.goals or [],
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/me/goals/{rsn}")
async def get_my_goals(
    rsn: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return the authenticated user's goals and share token for a linked RSN."""
    discord_user_id = int(current_user["sub"])
    result = await session.execute(
        select(
            MemberGoals.goals, MemberGoals.share_token, MemberGoals.updated_at
        ).where(
            MemberGoals.discord_user_id == discord_user_id,
            func.lower(MemberGoals.rsn) == rsn.lower(),
        )
    )
    row = result.one_or_none()
    if not row:
        return {"rsn": rsn, "goals": [], "share_token": None, "updated_at": None}
    return {
        "rsn": rsn,
        "goals": row.goals or [],
        "share_token": str(row.share_token),
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.put("/me/goals/{rsn}")
async def save_my_goals(
    rsn: str,
    body: GoalsSaveRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Upsert the authenticated user's goals for a linked RSN."""
    discord_user_id = int(current_user["sub"])

    owned = await session.execute(
        select(UserAccount.rsn).where(
            UserAccount.discord_user_id == discord_user_id,
            func.lower(UserAccount.rsn) == rsn.lower(),
        )
    )
    if not owned.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="RSN not linked to your account")

    now = datetime.now(UTC)
    stmt = pg_insert(MemberGoals).values(
        discord_user_id=discord_user_id,
        rsn=rsn.lower(),
        goals=body.goals,
        updated_at=now,
    )
    await session.execute(
        stmt.on_conflict_do_update(
            constraint="uq_member_goals_user_rsn",
            set_={"goals": stmt.excluded.goals, "updated_at": stmt.excluded.updated_at},
        )
    )
    await session.commit()

    token_result = await session.execute(
        select(MemberGoals.share_token).where(
            MemberGoals.discord_user_id == discord_user_id,
            func.lower(MemberGoals.rsn) == rsn.lower(),
        )
    )
    share_token = str(token_result.scalar_one())
    return {"rsn": rsn, "share_token": share_token, "updated_at": now.isoformat()}
