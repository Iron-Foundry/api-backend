from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Asset, Feedback
from app.dependencies import get_current_user, get_optional_user, get_session
from app.services.page_permissions import check_page_permission
from app.services.rank_mappings import get_effective_roles

from ._build import build_item
from ._helpers import (
    _ALLOWED_IMAGE_EXTS,
    _ALLOWED_IMAGE_TYPES,
    _MAX_IMAGE_BYTES,
    _VALID_TYPES,
    UPLOAD_DIR,
    EditFeedbackBody,
    SubmitFeedbackBody,
    UpdateStatusBody,
)

router = APIRouter()


@router.post("/upload-attachment")
async def upload_attachment(
    file: UploadFile = File(...),
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Upload an image attachment. Available to all authenticated members."""
    uid = int(current_user["sub"])

    if file.content_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            400, f"Only image files are allowed. Got: {file.content_type!r}"
        )

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
        created_at=datetime.now(UTC),
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


@router.get("/")
async def list_feedback(
    type: str | None = None,
    session: AsyncSession = Depends(get_session),
    current_user: dict[str, Any] | None = Depends(get_optional_user),
) -> list[dict[str, Any]]:
    current_user_id = int(current_user["sub"]) if current_user else None
    query = select(Feedback).order_by(Feedback.created_at.desc())
    if type is not None:
        if type not in _VALID_TYPES:
            raise HTTPException(400, f"type must be one of {_VALID_TYPES}")
        query = query.where(Feedback.type == type)
    result = await session.execute(query)
    items = result.scalars().all()
    return [await build_item(item, session, current_user_id) for item in items]


@router.post("/", status_code=201)
async def submit_feedback(
    body: SubmitFeedbackBody,
    session: AsyncSession = Depends(get_session),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    discord_user_id = int(current_user["sub"])
    now = datetime.now(UTC)
    extra: dict[str, Any] = {}
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
    return await build_item(item, session, discord_user_id)


@router.get("/{feedback_id}")
async def get_feedback(
    feedback_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: dict[str, Any] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    current_user_id = int(current_user["sub"]) if current_user else None
    item = await session.get(Feedback, feedback_id)
    if not item:
        raise HTTPException(404, "Feedback item not found")
    return await build_item(item, session, current_user_id, include_replies=True)


@router.patch("/{feedback_id}")
async def edit_feedback(
    feedback_id: int,
    body: EditFeedbackBody,
    session: AsyncSession = Depends(get_session),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    discord_user_id = int(current_user["sub"])
    item = await session.get(Feedback, feedback_id)
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
    item.updated_at = datetime.now(UTC)

    await session.commit()
    await session.refresh(item)
    return await build_item(item, session, discord_user_id)


@router.patch("/{feedback_id}/status")
async def update_status(
    feedback_id: int,
    body: UpdateStatusBody,
    session: AsyncSession = Depends(get_session),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    discord_user_id = int(current_user["sub"])
    roles = await get_effective_roles(discord_user_id, session)
    if not await check_page_permission("staff.feedback", "edit", roles, session):
        raise HTTPException(403, "Staff permission required to update feedback status")
    item = await session.get(Feedback, feedback_id)
    if not item:
        raise HTTPException(404, "Feedback item not found")
    item.status = body.status
    item.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(item)
    return await build_item(item, session, discord_user_id)
