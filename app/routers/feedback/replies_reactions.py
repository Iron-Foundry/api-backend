from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Feedback, FeedbackReaction, FeedbackReply
from app.dependencies import get_current_user, get_session
from app.services.page_permissions import check_page_permission
from app.services.rank_mappings import get_effective_roles

from ._helpers import PostReplyBody, get_user_info, serialize_reply

router = APIRouter()


@router.post("/{feedback_id}/react", status_code=200)
async def toggle_react(
    feedback_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Add or remove the caller's reaction on a feedback thread."""
    discord_user_id = int(current_user["sub"])
    item = await session.get(Feedback, feedback_id)
    if not item:
        raise HTTPException(404, "Feedback item not found")

    existing = (
        await session.execute(
            select(FeedbackReaction).where(
                FeedbackReaction.feedback_id == feedback_id,
                FeedbackReaction.discord_user_id == discord_user_id,
            )
        )
    ).scalar_one_or_none()

    if existing:
        await session.delete(existing)
        hearted = False
    else:
        session.add(
            FeedbackReaction(
                feedback_id=feedback_id,
                discord_user_id=discord_user_id,
                created_at=datetime.now(UTC),
            )
        )
        hearted = True

    await session.commit()
    heart_count = (
        await session.execute(
            select(func.count()).where(FeedbackReaction.feedback_id == feedback_id)
        )
    ).scalar_one()
    return {"hearted": hearted, "heart_count": heart_count}


@router.post("/{feedback_id}/replies", status_code=201)
async def post_reply(
    feedback_id: int,
    body: PostReplyBody,
    session: AsyncSession = Depends(get_session),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Reply to a feedback thread."""
    discord_user_id = int(current_user["sub"])
    item = await session.get(Feedback, feedback_id)
    if not item:
        raise HTTPException(404, "Feedback item not found")

    now = datetime.now(UTC)
    reply = FeedbackReply(
        feedback_id=feedback_id,
        discord_user_id=discord_user_id,
        body=body.body,
        is_pinned=False,
        created_at=now,
        updated_at=now,
    )
    session.add(reply)
    await session.commit()
    await session.refresh(reply)

    if item.is_anonymous and discord_user_id == item.discord_user_id:
        return serialize_reply(reply, None, None)
    author_name, author_clan_rank = await get_user_info(discord_user_id, session)
    return serialize_reply(reply, author_name, author_clan_rank)


@router.patch("/{feedback_id}/replies/{reply_id}/pin", status_code=200)
async def pin_reply(
    feedback_id: int,
    reply_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Pin a reply (staff only). Unpins any previously pinned reply on this item."""
    discord_user_id = int(current_user["sub"])
    roles = await get_effective_roles(discord_user_id, session)
    if not await check_page_permission("staff.feedback", "edit", roles, session):
        raise HTTPException(403, "Staff permission required to pin replies")

    reply = await session.get(FeedbackReply, reply_id)
    if not reply or reply.feedback_id != feedback_id:
        raise HTTPException(404, "Reply not found")

    for pinned in (
        (
            await session.execute(
                select(FeedbackReply).where(
                    FeedbackReply.feedback_id == feedback_id,
                    FeedbackReply.is_pinned == True,  # noqa: E712
                )
            )
        )
        .scalars()
        .all()
    ):
        pinned.is_pinned = False

    reply.is_pinned = True
    reply.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(reply)

    author_name, author_clan_rank = await get_user_info(reply.discord_user_id, session)
    return serialize_reply(reply, author_name, author_clan_rank)


@router.delete("/{feedback_id}/replies/{reply_id}/pin", status_code=200)
async def unpin_reply(
    feedback_id: int,
    reply_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Unpin a reply (staff only)."""
    discord_user_id = int(current_user["sub"])
    roles = await get_effective_roles(discord_user_id, session)
    if not await check_page_permission("staff.feedback", "edit", roles, session):
        raise HTTPException(403, "Staff permission required to unpin replies")

    reply = await session.get(FeedbackReply, reply_id)
    if not reply or reply.feedback_id != feedback_id:
        raise HTTPException(404, "Reply not found")

    reply.is_pinned = False
    reply.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(reply)

    author_name, author_clan_rank = await get_user_info(reply.discord_user_id, session)
    return serialize_reply(reply, author_name, author_clan_rank)


@router.delete("/{feedback_id}/replies/{reply_id}", status_code=204)
async def delete_reply(
    feedback_id: int,
    reply_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> None:
    """Delete a reply. Restricted to its author or staff."""
    discord_user_id = int(current_user["sub"])
    reply = await session.get(FeedbackReply, reply_id)
    if not reply or reply.feedback_id != feedback_id:
        raise HTTPException(404, "Reply not found")

    if reply.discord_user_id != discord_user_id:
        roles = await get_effective_roles(discord_user_id, session)
        if not await check_page_permission("staff.feedback", "edit", roles, session):
            raise HTTPException(403, "Cannot delete another user's reply")

    await session.delete(reply)
    await session.commit()
