from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PartyNotificationPreferences
from app.dependencies import get_current_user, get_session

from ._helpers import UpdateNotificationPrefsRequest

router = APIRouter()


@router.get("/notifications")
async def get_notification_preferences(
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return the current user's party notification preferences."""
    uid = int(current_user["sub"])
    result = await session.execute(
        select(PartyNotificationPreferences).where(
            PartyNotificationPreferences.user_id == uid
        )
    )
    prefs = result.scalar_one_or_none()
    return {"category_ids": prefs.category_ids if prefs else []}


@router.put("/notifications")
async def update_notification_preferences(
    body: UpdateNotificationPrefsRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Upsert the current user's party notification preferences."""
    uid = int(current_user["sub"])
    await session.execute(
        pg_insert(PartyNotificationPreferences)
        .values(user_id=uid, category_ids=body.category_ids)
        .on_conflict_do_update(
            index_elements=["user_id"], set_={"category_ids": body.category_ids}
        )
    )
    await session.commit()
    return {"category_ids": body.category_ids}
