from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from PIL import Image

THUMBNAIL_WIDTHS = (128, 256, 512)
THUMBNAIL_DIR_NAME = "thumbs"

_THUMBNAILABLE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/avif",
}


def supports_thumbnail(content_type: str | None) -> bool:
    """Whether a raster thumbnail can be derived from this content type."""
    return content_type in _THUMBNAILABLE_TYPES


def thumbnail_path(upload_dir: Path, filename: str, width: int) -> Path:
    return upload_dir / THUMBNAIL_DIR_NAME / f"{filename}.{width}.webp"


def _render(source: Path, target: Path, width: int) -> None:
    with Image.open(source) as img:
        frame = img.convert("RGBA" if img.mode in ("P", "LA", "RGBA") else "RGB")
        frame.thumbnail((width, width), Image.Resampling.LANCZOS)
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = target.with_name(f"{target.name}.{uuid.uuid4().hex}.tmp")
        frame.save(staging, format="WEBP", quality=80, method=4)
        staging.replace(target)


async def ensure_thumbnail(upload_dir: Path, filename: str, width: int) -> Path:
    """Path to the cached thumbnail, rendering it on first request.

    Stored filenames are immutable UUIDs, so a rendered thumbnail never goes
    stale and is reused until the asset is deleted.
    """
    target = thumbnail_path(upload_dir, filename, width)
    if target.exists():
        return target
    await asyncio.to_thread(_render, upload_dir / filename, target, width)
    return target


def purge_thumbnails(upload_dir: Path, filename: str) -> None:
    """Drop every cached thumbnail for an asset that is being deleted."""
    for width in THUMBNAIL_WIDTHS:
        thumbnail_path(upload_dir, filename, width).unlink(missing_ok=True)
