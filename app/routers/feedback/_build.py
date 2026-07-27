from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Feedback, FeedbackReaction, FeedbackReply

from ._helpers import get_user_info, get_username, resolve_attachments, serialize_reply


async def build_item(
    item: Feedback,
    session: AsyncSession,
    current_user_id: int | None,
    include_replies: bool = False,
) -> dict[str, Any]:
    is_own = current_user_id == item.discord_user_id

    if item.is_anonymous and not is_own:
        author_name = None
        author_discord_id = None
    else:
        author_name = await get_username(item.discord_user_id, session)
        author_discord_id = item.discord_user_id

    heart_count = (
        await session.execute(
            select(func.count()).where(FeedbackReaction.feedback_id == item.id)
        )
    ).scalar_one()

    is_hearted = False
    if current_user_id is not None:
        is_hearted = (
            await session.execute(
                select(FeedbackReaction).where(
                    FeedbackReaction.feedback_id == item.id,
                    FeedbackReaction.discord_user_id == current_user_id,
                )
            )
        ).scalar_one_or_none() is not None

    reply_count = (
        await session.execute(
            select(func.count()).where(FeedbackReply.feedback_id == item.id)
        )
    ).scalar_one()

    last_reply_at_raw = (
        await session.execute(
            select(func.max(FeedbackReply.created_at)).where(
                FeedbackReply.feedback_id == item.id
            )
        )
    ).scalar_one_or_none()

    pinned_reply_row = (
        await session.execute(
            select(FeedbackReply).where(
                FeedbackReply.feedback_id == item.id,
                FeedbackReply.is_pinned == True,  # noqa: E712
            )
        )
    ).scalar_one_or_none()

    pinned_reply = None
    if pinned_reply_row:
        if (
            item.is_anonymous
            and pinned_reply_row.discord_user_id == item.discord_user_id
        ):
            pinned_reply = serialize_reply(pinned_reply_row, None, None)
        else:
            pinned_author, pinned_clan_rank = await get_user_info(
                pinned_reply_row.discord_user_id, session
            )
            pinned_reply = serialize_reply(
                pinned_reply_row, pinned_author, pinned_clan_rank
            )

    attachments = await resolve_attachments(item.attachment_ids or [], session)

    result: dict[str, Any] = {
        "id": item.id,
        "type": item.type,
        "title": item.title,
        "description": item.description,
        "extra": item.extra,
        "status": item.status,
        "is_anonymous": item.is_anonymous,
        "author_name": author_name,
        "author_discord_id": author_discord_id,
        "is_own": is_own,
        "heart_count": heart_count,
        "is_hearted": is_hearted,
        "reply_count": reply_count,
        "last_reply_at": last_reply_at_raw.isoformat() if last_reply_at_raw else None,
        "pinned_reply": pinned_reply,
        "attachments": attachments,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }

    if include_replies:
        replies = (
            (
                await session.execute(
                    select(FeedbackReply)
                    .where(FeedbackReply.feedback_id == item.id)
                    .order_by(FeedbackReply.created_at)
                )
            )
            .scalars()
            .all()
        )
        serialized_replies = []
        for r in replies:
            if item.is_anonymous and r.discord_user_id == item.discord_user_id:
                serialized_replies.append(serialize_reply(r, None, None))
            else:
                r_author, r_clan_rank = await get_user_info(r.discord_user_id, session)
                serialized_replies.append(serialize_reply(r, r_author, r_clan_rank))
        result["replies"] = serialized_replies

    return result
