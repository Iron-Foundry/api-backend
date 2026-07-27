from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Badge
from app.dependencies import get_current_user, get_session

from ._helpers import BadgeBody, require_mentor, require_senior_mod, serialize_badge

router = APIRouter()


@router.get("/")
async def list_badges(
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=200),
) -> list[dict[str, Any]]:
    result = await session.execute(
        select(Badge).order_by(Badge.name).offset(skip).limit(limit)
    )
    return [serialize_badge(b) for b in result.scalars()]


@router.post("/")
async def create_badge(
    body: BadgeBody,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await require_mentor(current_user, session)
    badge = Badge(
        id=uuid.uuid4(),
        name=body.name.strip(),
        description=body.description.strip(),
        icon=body.icon,
        color=body.color,
        text_color=body.text_color,
        created_at=datetime.now(UTC),
        created_by=int(current_user["sub"]),
    )
    session.add(badge)
    await session.commit()
    return serialize_badge(badge)


@router.put("/{badge_id}")
async def update_badge(
    badge_id: UUID,
    body: BadgeBody,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await require_mentor(current_user, session)
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
    return serialize_badge(badge)


@router.delete("/{badge_id}")
async def delete_badge(
    badge_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await require_senior_mod(current_user, session)
    result = await session.execute(select(Badge).where(Badge.id == badge_id))
    badge = result.scalar_one_or_none()
    if not badge:
        raise HTTPException(404, "Badge not found.")
    await session.delete(badge)
    await session.commit()
    return {"ok": True}


@router.get("/{badge_id}")
async def get_badge(
    badge_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    result = await session.execute(select(Badge).where(Badge.id == badge_id))
    badge = result.scalar_one_or_none()
    if not badge:
        raise HTTPException(404, "Badge not found.")
    return serialize_badge(badge)
