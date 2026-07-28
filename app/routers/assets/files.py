from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Asset
from app.dependencies import get_session
from app.docs import responses
from app.services.asset_thumbnails import (
    THUMBNAIL_WIDTHS,
    ensure_thumbnail,
    supports_thumbnail,
)

from ._shared import IMMUTABLE_CACHE_HEADERS, UPLOAD_DIR

router = APIRouter(prefix="/assets", tags=["assets"], responses=responses.PUBLIC_LOOKUP)


@router.get("/file/{filename}")
async def serve_file(
    filename: str,
    w: int | None = Query(
        None, description="Thumbnail width. Raster images only; omit for the original."
    ),
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    """Serve an uploaded asset, optionally downscaled to a cached thumbnail."""
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Invalid filename")

    if w is not None and w not in THUMBNAIL_WIDTHS:
        allowed = ", ".join(str(width) for width in THUMBNAIL_WIDTHS)
        raise HTTPException(400, f"Thumbnail width must be one of: {allowed}")

    file_path = UPLOAD_DIR / filename
    if not file_path.exists():
        raise HTTPException(404, "File not found")

    result = await session.execute(select(Asset).where(Asset.filename == filename))
    asset = result.scalar_one_or_none()
    media_type = asset.content_type if asset else None

    if w is not None and supports_thumbnail(media_type):
        try:
            thumbnail = await ensure_thumbnail(UPLOAD_DIR, filename, w)
            return FileResponse(
                thumbnail,
                media_type="image/webp",
                headers=IMMUTABLE_CACHE_HEADERS,
            )
        except (OSError, ValueError) as exc:
            logger.warning(f"Thumbnail failed for {filename} at {w}px: {exc}")

    return FileResponse(
        file_path, media_type=media_type, headers=IMMUTABLE_CACHE_HEADERS
    )
