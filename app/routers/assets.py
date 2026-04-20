import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Asset, User
from app.dependencies import get_current_user, get_session
from app.routers.surveys import _has_min_rank
from app.services.rank_mappings import get_effective_roles

router = APIRouter(prefix="/assets", tags=["assets"])

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/app/uploads"))
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_VIDEO_BYTES = 100 * 1024 * 1024

ALLOWED_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/svg+xml",
    "image/avif",
    "video/mp4",
    "video/webm",
    "video/ogg",
}

ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".avif", ".mp4", ".webm", ".ogg"}


@router.get("/file/{filename}")
async def serve_file(
    filename: str,
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Invalid filename")
    file_path = UPLOAD_DIR / filename
    if not file_path.exists():
        raise HTTPException(404, "File not found")
    result = await session.execute(select(Asset).where(Asset.filename == filename))
    asset = result.scalar_one_or_none()
    media_type = asset.content_type if asset else None
    return FileResponse(file_path, media_type=media_type)


@router.get("")
async def list_assets(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    result = await session.execute(
        select(Asset, User)
        .join(User, Asset.uploaded_by == User.discord_user_id, isouter=True)
        .order_by(Asset.created_at.desc())
    )
    return [
        {
            "id": str(a.id),
            "filename": a.filename,
            "original_name": a.original_name,
            "content_type": a.content_type,
            "size_bytes": a.size_bytes,
            "url": f"/assets/file/{a.filename}",
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "uploaded_by": {
                "discord_user_id": u.discord_user_id,
                "rsn": u.rsn,
                "discord_username": u.discord_username,
            } if u else None,
        }
        for a, u in result.all()
    ]


@router.post("/upload")
async def upload_asset(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    uid = int(current_user["sub"])
    roles = await get_effective_roles(uid, session)
    if not _has_min_rank(roles, "Foundry Mentors"):
        raise HTTPException(403, "Foundry Mentors+ required to upload assets")

    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"File type {file.content_type!r} not allowed. Allowed: {', '.join(sorted(ALLOWED_TYPES))}")

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
        created_at=datetime.now(timezone.utc),
    )
    session.add(asset)
    await session.commit()
    await session.refresh(asset)

    return {
        "id": str(asset.id),
        "filename": asset.filename,
        "original_name": asset.original_name,
        "content_type": asset.content_type,
        "size_bytes": asset.size_bytes,
        "url": f"/assets/file/{asset.filename}",
        "created_at": asset.created_at.isoformat() if asset.created_at else None,
    }


@router.delete("/{asset_id}")
async def delete_asset(
    asset_id: UUID,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    uid = int(current_user["sub"])
    roles = await get_effective_roles(uid, session)
    is_senior_mod = _has_min_rank(roles, "Senior Moderator")

    asset = await session.get(Asset, asset_id)
    if not asset:
        raise HTTPException(404, "Asset not found")

    if not is_senior_mod and asset.uploaded_by != uid:
        raise HTTPException(403, "You can only delete your own uploads")

    file_path = UPLOAD_DIR / asset.filename
    if file_path.exists():
        file_path.unlink()

    await session.delete(asset)
    await session.commit()
    return {"ok": True}
