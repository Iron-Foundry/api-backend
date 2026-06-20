from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContentCategory, ContentEntry, User
from app.dependencies import get_current_user, get_session

from ._helpers import _require_senior_mod

router = APIRouter()


@router.get("/deprecated-entries")
async def get_deprecated_entries(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    await _require_senior_mod(current_user, session)

    result = await session.execute(
        select(ContentEntry, ContentCategory, User)
        .join(ContentCategory, ContentEntry.category_id == ContentCategory.id)
        .join(User, User.discord_user_id == ContentEntry.deprecated_by, isouter=True)
        .where(ContentEntry.deprecated == True)  # noqa: E712
        .order_by(ContentEntry.deprecated_at.desc())
    )
    return [
        {
            "id": str(e.id),
            "title": e.title,
            "slug": e.slug,
            "page_type": cat.page_type,
            "deprecated_at": e.deprecated_at.isoformat() if e.deprecated_at else None,
            "deprecated_by": {
                "discord_user_id": u.discord_user_id,
                "discord_username": u.discord_username,
                "rsn": u.rsn,
                "avatar": u.discord_avatar_url,
            }
            if u
            else None,
        }
        for e, cat, u in result.all()
    ]
