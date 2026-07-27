from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Asset, User
from app.dependencies import get_current_user, get_session
from app.services.asset_thumbnails import purge_thumbnails
from app.services.page_permissions import check_page_permission
from app.services.rank_mappings import get_effective_roles

from ._shared import (
    ALLOWED_EXTS,
    ALLOWED_TYPES,
    MAX_IMAGE_BYTES,
    MAX_VIDEO_BYTES,
    UPLOAD_DIR,
    serialize_asset,
)

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("")
async def list_assets(
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    result = await session.execute(
        select(Asset, User)
        .join(User, Asset.uploaded_by == User.discord_user_id, isouter=True)
        .order_by(Asset.created_at.desc())
    )
    return [serialize_asset(asset, uploader) for asset, uploader in result.all()]


@router.post("/upload")
async def upload_asset(
    file: UploadFile = File(...),
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    uid = int(current_user["sub"])
    roles = await get_effective_roles(uid, session)
    if not await check_page_permission("resources", "create", roles, session):
        raise HTTPException(403, "Foundry Mentors+ required to upload assets")

    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            400,
            f"File type {file.content_type!r} not allowed. "
            f"Allowed: {', '.join(sorted(ALLOWED_TYPES))}",
        )

    original_name = file.filename or "upload"
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(400, f"Extension {ext!r} not allowed")

    is_video = file.content_type.startswith("video/")
    max_bytes = MAX_VIDEO_BYTES if is_video else MAX_IMAGE_BYTES
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        limit_str = "100 MB" if is_video else "10 MB"
        raise HTTPException(400, f"File exceeds {limit_str} limit")

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

    return serialize_asset(asset)


@router.delete("/{asset_id}")
async def delete_asset(
    asset_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    uid = int(current_user["sub"])
    roles = await get_effective_roles(uid, session)
    is_senior_mod = await check_page_permission("resources", "delete", roles, session)

    asset = await session.get(Asset, asset_id)
    if not asset:
        raise HTTPException(404, "Asset not found")

    if not is_senior_mod and asset.uploaded_by != uid:
        raise HTTPException(403, "You can only delete your own uploads")

    file_path = UPLOAD_DIR / asset.filename
    if file_path.exists():
        file_path.unlink()
    purge_thumbnails(UPLOAD_DIR, asset.filename)

    await session.delete(asset)
    await session.commit()
    return {"ok": True}
