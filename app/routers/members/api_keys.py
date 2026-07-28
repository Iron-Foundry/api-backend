from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.dependencies import get_current_user, get_session

router = APIRouter()


@router.get("/me/api-key")
async def get_api_key(
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return the member's personal API key, creating one on first request."""
    discord_user_id = int(current_user["sub"])
    result = await session.execute(
        select(User.api_key, User.key_is_active, User.key_created_at).where(
            User.discord_user_id == discord_user_id
        )
    )
    row = result.one_or_none()
    if not row or not row.api_key:
        return {"key": None, "is_active": False, "created_at": None}
    return {
        "key": row.api_key,
        "is_active": row.key_is_active,
        "created_at": row.key_created_at.isoformat() if row.key_created_at else None,
    }


@router.post("/me/api-key/rotate")
async def rotate_api_key(
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Issue a new API key and immediately revoke the old one."""
    discord_user_id = int(current_user["sub"])
    new_key = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    await session.execute(
        update(User)
        .where(User.discord_user_id == discord_user_id)
        .values(api_key=new_key, key_is_active=True, key_created_at=now, updated_at=now)
    )
    await session.commit()
    logger.info("members/api-key: user {} rotated API key", discord_user_id)
    return {"key": new_key, "is_active": True, "created_at": now.isoformat()}
