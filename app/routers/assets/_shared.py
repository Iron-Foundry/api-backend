from __future__ import annotations

import os
from pathlib import Path

from app.db.models import Asset, User

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/app/uploads"))
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_VIDEO_BYTES = 100 * 1024 * 1024

IMMUTABLE_CACHE_HEADERS = {"Cache-Control": "public, max-age=31536000, immutable"}

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

ALLOWED_EXTS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".avif",
    ".mp4",
    ".webm",
    ".ogg",
}


def serialize_asset(asset: Asset, uploader: User | None = None) -> dict:
    return {
        "id": str(asset.id),
        "filename": asset.filename,
        "original_name": asset.original_name,
        "content_type": asset.content_type,
        "size_bytes": asset.size_bytes,
        "url": f"/assets/file/{asset.filename}",
        "created_at": asset.created_at.isoformat() if asset.created_at else None,
        "uploaded_by": {
            "discord_user_id": uploader.discord_user_id,
            "rsn": uploader.rsn,
            "discord_username": uploader.discord_username,
        }
        if uploader
        else None,
    }
