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
MAX_BYTES = 10 * 1024 * 1024  # 10 MB

ALLOWED_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/svg+xml",
    "image/avif",
}

ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".avif"}


# ── Public file serving ────────────────────────────────────────────────────────

@router.get("/file/{filename}")
async def serve_file(filename: str) -> FileResponse:
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Invalid filename")
    file_path = UPLOAD_DIR / filename
    if not file_path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(file_path)


# ── Auth-gated endpoints ───────────────────────────────────────────────────────

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
    if not _has_min_rank(roles, "Mentor"):
        raise HTTPException(403, "Mentor+ required to upload assets")

    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"File type {file.content_type!r} not allowed. Allowed: {', '.join(sorted(ALLOWED_TYPES))}")

    original_name = file.filename or "upload"
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(400, f"Extension {ext!r} not allowed")

    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(400, "File exceeds 10 MB limit")

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
