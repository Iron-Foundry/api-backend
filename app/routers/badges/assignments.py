from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Badge, User, UserBadge
from app.dependencies import get_current_user, get_session

from ._helpers import AssignBody, require_mentor, serialize_badge

router = APIRouter()


@router.get("/{badge_id}/members")
async def badge_members(
    badge_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """List the members currently holding this badge."""
    await require_mentor(current_user, session)
    result = await session.execute(
        select(UserBadge, User.discord_username, User.rsn)
        .join(User, User.discord_user_id == UserBadge.discord_user_id)
        .where(UserBadge.badge_id == badge_id)
        .order_by(UserBadge.assigned_at)
    )
    return [
        {
            "discord_user_id": ub.discord_user_id,
            "username": username,
            "rsn": rsn,
            "assigned_at": ub.assigned_at.isoformat() if ub.assigned_at else None,
        }
        for ub, username, rsn in result
    ]


@router.post("/{badge_id}/assign")
async def assign_badge(
    badge_id: UUID,
    body: AssignBody,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Grant this badge to a member. Staff only."""
    await require_mentor(current_user, session)
    badge = (
        await session.execute(select(Badge).where(Badge.id == badge_id))
    ).scalar_one_or_none()
    if not badge:
        raise HTTPException(404, "Badge not found.")
    await session.execute(
        pg_insert(UserBadge)
        .values(
            badge_id=badge_id,
            discord_user_id=body.discord_user_id,
            assigned_at=datetime.now(UTC),
            assigned_by=int(current_user["sub"]),
        )
        .on_conflict_do_nothing(constraint="user_badges_badge_id_discord_user_id_key")
    )
    await session.commit()
    return {"ok": True}


@router.delete("/{badge_id}/assign/{user_id}")
async def revoke_badge(
    badge_id: UUID,
    user_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Revoke this badge from a member. Staff only."""
    await require_mentor(current_user, session)
    await session.execute(
        delete(UserBadge).where(
            UserBadge.badge_id == badge_id, UserBadge.discord_user_id == user_id
        )
    )
    await session.commit()
    return {"ok": True}


@router.get("/me")
async def my_badges(
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """List the badges held by the signed-in member."""
    uid = int(current_user["sub"])
    result = await session.execute(
        select(Badge, UserBadge.assigned_at)
        .join(UserBadge, UserBadge.badge_id == Badge.id)
        .where(UserBadge.discord_user_id == uid)
        .order_by(UserBadge.assigned_at)
    )
    return [
        {
            **serialize_badge(b),
            "assigned_at": assigned_at.isoformat() if assigned_at else None,
        }
        for b, assigned_at in result
    ]
