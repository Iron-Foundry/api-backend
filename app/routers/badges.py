"""Badges router - create, manage, and assign profile badges."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Badge, User, UserBadge
from app.dependencies import get_current_user, get_session
from app.services.page_permissions import check_page_permission
from app.services.rank_mappings import get_effective_roles

router = APIRouter(prefix="/badges", tags=["badges"])


async def _require_mentor(current_user: dict, session: AsyncSession) -> None:
    uid = int(current_user["sub"])
    roles = await get_effective_roles(uid, session)
    if not await check_page_permission("staff.badges", "create", roles, session):
        raise HTTPException(403, "Requires Mentor or higher.")


async def _require_senior_mod(current_user: dict, session: AsyncSession) -> None:
    uid = int(current_user["sub"])
    roles = await get_effective_roles(uid, session)
    if not await check_page_permission("staff.badges", "delete", roles, session):
        raise HTTPException(403, "Requires Senior Moderator or higher.")


class BadgeBody(BaseModel):
    name: str
    description: str = ""
    icon: str | None = None
    color: str = "#6366f1"
    text_color: str = "#ffffff"


@router.get("")
async def list_badges(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=200),
) -> list[dict]:
    """Return all badges. Any authenticated user can fetch the list."""
    result = await session.execute(select(Badge).order_by(Badge.name).offset(skip).limit(limit))
    return [
        {
            "id": str(b.id),
            "name": b.name,
            "description": b.description,
            "icon": b.icon,
            "color": b.color,
            "text_color": b.text_color,
            "created_at": b.created_at.isoformat() if b.created_at else None,
        }
        for b in result.scalars()
    ]


@router.post("")
async def create_badge(
    body: BadgeBody,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Create a badge. Requires Mentor or higher."""
    await _require_mentor(current_user, session)
    badge = Badge(
        id=uuid.uuid4(),
        name=body.name.strip(),
        description=body.description.strip(),
        icon=body.icon,
        color=body.color,
        text_color=body.text_color,
        created_at=datetime.now(timezone.utc),
        created_by=int(current_user["sub"]),
    )
    session.add(badge)
    await session.commit()
    return {
        "id": str(badge.id),
        "name": badge.name,
        "description": badge.description,
        "icon": badge.icon,
        "color": badge.color,
        "text_color": badge.text_color,
        "created_at": badge.created_at.isoformat() if badge.created_at else None,
    }


@router.put("/{badge_id}")
async def update_badge(
    badge_id: UUID,
    body: BadgeBody,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Update a badge. Requires Mentor or higher."""
    await _require_mentor(current_user, session)
    result = await session.execute(select(Badge).where(Badge.id == badge_id))
    badge = result.scalar_one_or_none()
    if not badge:
        raise HTTPException(404, "Badge not found.")
    badge.name = body.name.strip()
    badge.description = body.description.strip()
    badge.icon = body.icon
    badge.color = body.color
    badge.text_color = body.text_color
    await session.commit()
    return {
        "id": str(badge.id),
        "name": badge.name,
        "description": badge.description,
        "icon": badge.icon,
        "color": badge.color,
        "text_color": badge.text_color,
        "created_at": badge.created_at.isoformat() if badge.created_at else None,
    }


@router.delete("/{badge_id}")
async def delete_badge(
    badge_id: UUID,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Delete a badge. Requires Senior Moderator or higher."""
    await _require_senior_mod(current_user, session)
    result = await session.execute(select(Badge).where(Badge.id == badge_id))
    badge = result.scalar_one_or_none()
    if not badge:
        raise HTTPException(404, "Badge not found.")
    await session.delete(badge)
    await session.commit()
    return {"ok": True}


class AssignBody(BaseModel):
    discord_user_id: int


@router.get("/{badge_id}/members")
async def badge_members(
    badge_id: UUID,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """List members who hold this badge. Requires Mentor or higher."""
    await _require_mentor(current_user, session)
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
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Assign a badge to a member. Requires Mentor or higher."""
    await _require_mentor(current_user, session)
    badge = (
        await session.execute(select(Badge).where(Badge.id == badge_id))
    ).scalar_one_or_none()
    if not badge:
        raise HTTPException(404, "Badge not found.")
    stmt = (
        pg_insert(UserBadge)
        .values(
            badge_id=badge_id,
            discord_user_id=body.discord_user_id,
            assigned_at=datetime.now(timezone.utc),
            assigned_by=int(current_user["sub"]),
        )
        .on_conflict_do_nothing(constraint="user_badges_badge_id_discord_user_id_key")
    )
    await session.execute(stmt)
    await session.commit()
    return {"ok": True}


@router.delete("/{badge_id}/assign/{discord_user_id}")
async def revoke_badge(
    badge_id: UUID,
    discord_user_id: int,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Revoke a badge from a member. Requires Mentor or higher."""
    await _require_mentor(current_user, session)
    await session.execute(
        delete(UserBadge).where(
            UserBadge.badge_id == badge_id,
            UserBadge.discord_user_id == discord_user_id,
        )
    )
    await session.commit()
    return {"ok": True}


@router.get("/me")
async def my_badges(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Return the authenticated user's earned badges."""
    uid = int(current_user["sub"])
    result = await session.execute(
        select(Badge)
        .join(UserBadge, UserBadge.badge_id == Badge.id)
        .where(UserBadge.discord_user_id == uid)
        .order_by(UserBadge.assigned_at)
    )
    return [
        {
            "id": str(b.id),
            "name": b.name,
            "description": b.description,
            "icon": b.icon,
            "color": b.color,
            "text_color": b.text_color,
        }
        for b in result.scalars()
    ]


@router.get("/{badge_id}")
async def get_badge(
    badge_id: UUID,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return a single badge by ID. Any authenticated user."""
    result = await session.execute(select(Badge).where(Badge.id == badge_id))
    badge = result.scalar_one_or_none()
    if not badge:
        raise HTTPException(404, "Badge not found.")
    return {
        "id": str(badge.id),
        "name": badge.name,
        "description": badge.description,
        "icon": badge.icon,
        "color": badge.color,
        "text_color": badge.text_color,
        "created_at": badge.created_at.isoformat() if badge.created_at else None,
    }
