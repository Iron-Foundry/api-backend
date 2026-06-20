from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContentEntryReaction
from app.dependencies import get_current_user, get_session

from ._helpers import _validate_page_type

router = APIRouter()


@router.post("/{page_type}/entries/{entry_id}/react")
async def toggle_reaction(
    page_type: str,
    entry_id: UUID,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Toggle a heart reaction on a content entry. Returns updated reacted state and count."""
    _validate_page_type(page_type)
    uid = int(current_user["sub"])
    now = datetime.now(timezone.utc)

    existing = (
        await session.execute(
            select(ContentEntryReaction).where(
                ContentEntryReaction.entry_id == entry_id,
                ContentEntryReaction.discord_user_id == uid,
            )
        )
    ).scalar_one_or_none()

    if existing:
        await session.delete(existing)
        reacted = False
    else:
        session.add(
            ContentEntryReaction(entry_id=entry_id, discord_user_id=uid, created_at=now)
        )
        reacted = True

    await session.commit()

    count_result = await session.execute(
        select(func.count())
        .select_from(ContentEntryReaction)
        .where(ContentEntryReaction.entry_id == entry_id)
    )
    return {"reacted": reacted, "count": count_result.scalar_one()}
