"""Feedback router - suggestions and bug reports from members."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
import os

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Asset, Feedback, FeedbackReaction, FeedbackReply, User
from app.dependencies import get_current_user, get_optional_user, get_session
from app.services.page_permissions import check_page_permission
from app.services.rank_mappings import get_effective_roles

router = APIRouter(prefix="/feedback", tags=["feedback"])

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/app/uploads"))
_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/avif"}
_ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif"}
_MAX_IMAGE_BYTES = 10 * 1024 * 1024

_VALID_TYPES = ("suggestion", "bug")
_VALID_STATUSES = ("open", "in-review", "implemented", "wont-fix", "solved", "closed")


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class SubmitFeedbackBody(BaseModel):
    type: Literal["suggestion", "bug"]
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=4000)
    is_anonymous: bool = False
    steps_to_reproduce: str | None = Field(None, max_length=4000)
    attachment_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_steps_for_bugs(self) -> "SubmitFeedbackBody":
        if self.type == "bug" and not self.steps_to_reproduce:
            raise ValueError("steps_to_reproduce is required for bug reports")
        return self


class EditFeedbackBody(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, min_length=1, max_length=4000)
    steps_to_reproduce: str | None = Field(None, max_length=4000)
    is_anonymous: bool | None = None
    attachment_ids: list[str] | None = None


class UpdateStatusBody(BaseModel):
    status: Literal["open", "planned", "implemented", "needs-triage", "wont-add", "reviewing", "patched", "wont-fix"]


class PostReplyBody(BaseModel):
    body: str = Field(..., min_length=1, max_length=4000)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_username(discord_user_id: int, session: AsyncSession) -> str | None:
    result = await session.execute(
        select(User.discord_username).where(User.discord_user_id == discord_user_id)
    )
    return result.scalar_one_or_none()


async def _get_user_info(discord_user_id: int, session: AsyncSession) -> tuple[str | None, str | None]:
    """Return (discord_username, clan_rank)."""
    result = await session.execute(
        select(User.discord_username, User.clan_rank).where(User.discord_user_id == discord_user_id)
    )
    row = result.one_or_none()
    if row:
        return row.discord_username, row.clan_rank
    return None, None


async def _resolve_attachments(attachment_ids: list, session: AsyncSession) -> list[dict]:
    if not attachment_ids:
        return []
    results = []
    for aid in attachment_ids:
        try:
            asset_uuid = uuid.UUID(str(aid))
        except ValueError:
            continue
        asset = await session.get(Asset, asset_uuid)
        if asset:
            results.append({
                "id": str(asset.id),
                "url": f"/assets/file/{asset.filename}",
                "original_name": asset.original_name,
                "content_type": asset.content_type,
            })
    return results


def _serialize_reply(
    reply: FeedbackReply,
    author_name: str | None,
    author_clan_rank: str | None = None,
) -> dict:
    return {
        "id": reply.id,
        "feedback_id": reply.feedback_id,
        "body": reply.body,
        "is_pinned": reply.is_pinned,
        "author_name": author_name,
        "author_discord_id": reply.discord_user_id,
        "author_clan_rank": author_clan_rank,
        "created_at": reply.created_at.isoformat(),
        "updated_at": reply.updated_at.isoformat(),
    }


async def _build_item(
    item: Feedback,
    session: AsyncSession,
    current_user_id: int | None,
    include_replies: bool = False,
) -> dict:
    is_own = current_user_id == item.discord_user_id

    if item.is_anonymous and not is_own:
        author_name = None
        author_discord_id = None
    else:
        author_name = await _get_username(item.discord_user_id, session)
        author_discord_id = item.discord_user_id

    heart_count_result = await session.execute(
        select(func.count()).where(FeedbackReaction.feedback_id == item.id)
    )
    heart_count = heart_count_result.scalar_one()

    is_hearted = False
    if current_user_id is not None:
        hearted_result = await session.execute(
            select(FeedbackReaction).where(
                FeedbackReaction.feedback_id == item.id,
                FeedbackReaction.discord_user_id == current_user_id,
            )
        )
        is_hearted = hearted_result.scalar_one_or_none() is not None

    reply_count_result = await session.execute(
        select(func.count()).where(FeedbackReply.feedback_id == item.id)
    )
    reply_count = reply_count_result.scalar_one()

    last_reply_result = await session.execute(
        select(func.max(FeedbackReply.created_at)).where(FeedbackReply.feedback_id == item.id)
    )
    last_reply_at_raw = last_reply_result.scalar_one_or_none()
    last_reply_at = last_reply_at_raw.isoformat() if last_reply_at_raw else None

    pinned_result = await session.execute(
        select(FeedbackReply).where(
            FeedbackReply.feedback_id == item.id,
            FeedbackReply.is_pinned == True,  # noqa: E712
        )
    )
    pinned_reply_row = pinned_result.scalar_one_or_none()
    pinned_reply = None
    if pinned_reply_row:
        if item.is_anonymous and pinned_reply_row.discord_user_id == item.discord_user_id:
            pinned_reply = _serialize_reply(pinned_reply_row, None, None)
        else:
            pinned_author, pinned_clan_rank = await _get_user_info(pinned_reply_row.discord_user_id, session)
            pinned_reply = _serialize_reply(pinned_reply_row, pinned_author, pinned_clan_rank)

    attachments = await _resolve_attachments(item.attachment_ids or [], session)

    result: dict = {
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
        "last_reply_at": last_reply_at,
        "pinned_reply": pinned_reply,
        "attachments": attachments,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }

    if include_replies:
        replies_result = await session.execute(
            select(FeedbackReply)
            .where(FeedbackReply.feedback_id == item.id)
            .order_by(FeedbackReply.created_at)
        )
        replies = replies_result.scalars().all()
        serialized_replies = []
        for r in replies:
            if item.is_anonymous and r.discord_user_id == item.discord_user_id:
                serialized_replies.append(_serialize_reply(r, None, None))
            else:
                r_author, r_clan_rank = await _get_user_info(r.discord_user_id, session)
                serialized_replies.append(_serialize_reply(r, r_author, r_clan_rank))
        result["replies"] = serialized_replies

    return result


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/upload-attachment")
async def upload_attachment(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Upload an image attachment for a feedback item. Available to all authenticated members."""
    uid = int(current_user["sub"])

    if file.content_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(400, f"Only image files are allowed. Got: {file.content_type!r}")

    original_name = file.filename or "upload"
    ext = Path(original_name).suffix.lower()
    if ext not in _ALLOWED_IMAGE_EXTS:
        raise HTTPException(400, f"Extension {ext!r} not allowed")

    data = await file.read(_MAX_IMAGE_BYTES + 1)
    if len(data) > _MAX_IMAGE_BYTES:
        raise HTTPException(400, "Image exceeds 10 MB limit")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4()}{ext}"
    (UPLOAD_DIR / stored_name).write_bytes(data)

    asset = Asset(
        filename=stored_name,
        original_name=original_name,
        content_type=file.content_type,
        size_bytes=len(data),
        uploaded_by=uid,
        created_at=datetime.now(timezone.utc),
    )
    session.add(asset)
    await session.commit()
    await session.refresh(asset)

    return {
        "id": str(asset.id),
        "url": f"/assets/file/{asset.filename}",
        "original_name": asset.original_name,
        "content_type": asset.content_type,
    }


@router.get("")
async def list_feedback(
    type: str | None = None,
    session: AsyncSession = Depends(get_session),
    current_user: dict | None = Depends(get_optional_user),
) -> list[dict]:
    current_user_id = int(current_user["sub"]) if current_user else None

    query = select(Feedback).order_by(Feedback.created_at.desc())
    if type is not None:
        if type not in _VALID_TYPES:
            raise HTTPException(400, f"type must be one of {_VALID_TYPES}")
        query = query.where(Feedback.type == type)

    result = await session.execute(query)
    items = result.scalars().all()
    return [await _build_item(item, session, current_user_id) for item in items]


@router.post("", status_code=201)
async def submit_feedback(
    body: SubmitFeedbackBody,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    discord_user_id = int(current_user["sub"])
    now = datetime.now(timezone.utc)

    extra: dict = {}
    if body.type == "bug" and body.steps_to_reproduce:
        extra["steps_to_reproduce"] = body.steps_to_reproduce

    item = Feedback(
        type=body.type,
        discord_user_id=discord_user_id,
        is_anonymous=body.is_anonymous,
        title=body.title,
        description=body.description,
        extra=extra,
        status="open",
        attachment_ids=body.attachment_ids,
        created_at=now,
        updated_at=now,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return await _build_item(item, session, discord_user_id)


@router.get("/{item_id}")
async def get_feedback(
    item_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: dict | None = Depends(get_optional_user),
) -> dict:
    current_user_id = int(current_user["sub"]) if current_user else None
    item = await session.get(Feedback, item_id)
    if not item:
        raise HTTPException(404, "Feedback item not found")
    return await _build_item(item, session, current_user_id, include_replies=True)


@router.patch("/{item_id}")
async def edit_feedback(
    item_id: int,
    body: EditFeedbackBody,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    discord_user_id = int(current_user["sub"])
    item = await session.get(Feedback, item_id)
    if not item:
        raise HTTPException(404, "Feedback item not found")
    if item.discord_user_id != discord_user_id:
        raise HTTPException(403, "Not your feedback item")
    if item.status != "open":
        raise HTTPException(400, "Can only edit feedback while status is 'open'")

    if body.title is not None:
        item.title = body.title
    if body.description is not None:
        item.description = body.description
    if body.is_anonymous is not None:
        item.is_anonymous = body.is_anonymous
    if body.steps_to_reproduce is not None:
        extra = dict(item.extra)
        extra["steps_to_reproduce"] = body.steps_to_reproduce
        item.extra = extra
    if body.attachment_ids is not None:
        item.attachment_ids = body.attachment_ids
    item.updated_at = datetime.now(timezone.utc)

    await session.commit()
    await session.refresh(item)
    return await _build_item(item, session, discord_user_id)


@router.patch("/{item_id}/status")
async def update_status(
    item_id: int,
    body: UpdateStatusBody,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    discord_user_id = int(current_user["sub"])
    roles = await get_effective_roles(discord_user_id, session)
    if not await check_page_permission("staff.feedback", "edit", roles, session):
        raise HTTPException(403, "Staff permission required to update feedback status")

    item = await session.get(Feedback, item_id)
    if not item:
        raise HTTPException(404, "Feedback item not found")

    item.status = body.status
    item.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(item)
    return await _build_item(item, session, discord_user_id)


@router.post("/{item_id}/react", status_code=200)
async def toggle_react(
    item_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    discord_user_id = int(current_user["sub"])
    item = await session.get(Feedback, item_id)
    if not item:
        raise HTTPException(404, "Feedback item not found")

    existing = await session.execute(
        select(FeedbackReaction).where(
            FeedbackReaction.feedback_id == item_id,
            FeedbackReaction.discord_user_id == discord_user_id,
        )
    )
    reaction = existing.scalar_one_or_none()

    if reaction:
        await session.delete(reaction)
        hearted = False
    else:
        session.add(
            FeedbackReaction(
                feedback_id=item_id,
                discord_user_id=discord_user_id,
                created_at=datetime.now(timezone.utc),
            )
        )
        hearted = True

    await session.commit()

    heart_count_result = await session.execute(
        select(func.count()).where(FeedbackReaction.feedback_id == item_id)
    )
    return {"hearted": hearted, "heart_count": heart_count_result.scalar_one()}


@router.post("/{item_id}/replies", status_code=201)
async def post_reply(
    item_id: int,
    body: PostReplyBody,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    discord_user_id = int(current_user["sub"])
    item = await session.get(Feedback, item_id)
    if not item:
        raise HTTPException(404, "Feedback item not found")

    now = datetime.now(timezone.utc)
    reply = FeedbackReply(
        feedback_id=item_id,
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
        return _serialize_reply(reply, None, None)
    author_name, author_clan_rank = await _get_user_info(discord_user_id, session)
    return _serialize_reply(reply, author_name, author_clan_rank)


@router.patch("/{item_id}/replies/{reply_id}/pin", status_code=200)
async def pin_reply(
    item_id: int,
    reply_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Pin a reply (staff only). Unpins any previously pinned reply on this item."""
    discord_user_id = int(current_user["sub"])
    roles = await get_effective_roles(discord_user_id, session)
    if not await check_page_permission("staff.feedback", "edit", roles, session):
        raise HTTPException(403, "Staff permission required to pin replies")

    reply = await session.get(FeedbackReply, reply_id)
    if not reply or reply.feedback_id != item_id:
        raise HTTPException(404, "Reply not found")

    # Unpin any currently pinned reply on this item
    existing_pinned = await session.execute(
        select(FeedbackReply).where(
            FeedbackReply.feedback_id == item_id,
            FeedbackReply.is_pinned == True,  # noqa: E712
        )
    )
    for pinned in existing_pinned.scalars().all():
        pinned.is_pinned = False

    reply.is_pinned = True
    reply.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(reply)

    author_name, author_clan_rank = await _get_user_info(reply.discord_user_id, session)
    return _serialize_reply(reply, author_name, author_clan_rank)


@router.delete("/{item_id}/replies/{reply_id}/pin", status_code=200)
async def unpin_reply(
    item_id: int,
    reply_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Unpin a reply (staff only)."""
    discord_user_id = int(current_user["sub"])
    roles = await get_effective_roles(discord_user_id, session)
    if not await check_page_permission("staff.feedback", "edit", roles, session):
        raise HTTPException(403, "Staff permission required to unpin replies")

    reply = await session.get(FeedbackReply, reply_id)
    if not reply or reply.feedback_id != item_id:
        raise HTTPException(404, "Reply not found")

    reply.is_pinned = False
    reply.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(reply)

    author_name, author_clan_rank = await _get_user_info(reply.discord_user_id, session)
    return _serialize_reply(reply, author_name, author_clan_rank)


@router.delete("/{item_id}/replies/{reply_id}", status_code=204)
async def delete_reply(
    item_id: int,
    reply_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> None:
    discord_user_id = int(current_user["sub"])

    reply = await session.get(FeedbackReply, reply_id)
    if not reply or reply.feedback_id != item_id:
        raise HTTPException(404, "Reply not found")

    if reply.discord_user_id != discord_user_id:
        roles = await get_effective_roles(discord_user_id, session)
        if not await check_page_permission("staff.feedback", "edit", roles, session):
            raise HTTPException(403, "Cannot delete another user's reply")

    await session.delete(reply)
    await session.commit()
