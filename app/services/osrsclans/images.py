"""OSRSClans images served through Foundry and kept on Foundry's disk.

Every OSRS image a Foundry page or embed shows links to Foundry's own image
route. The first request for an image fetches it from OSRSClans once; each
later request reads the copy under the uploads volume, so a page of images never
reaches OSRSClans twice. A 404 is remembered for an hour.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode

from valkey.asyncio import Valkey

from app.services.osrsclans.client import (
    OsrsClansError,
    OsrsClansNotFoundError,
    guarded_get,
)

ImageKind = Literal["items", "npcs", "sprites"]
ImageFormat = Literal["webp", "svg"]
MEDIA_TYPES: dict[str, str] = {"webp": "image/webp", "svg": "image/svg+xml"}
_MISSING_PREFIX = "osrsclans:image-missing:"
_MISSING_TTL_SECONDS = 3600


def image_cache_dir() -> Path:
    """Return the folder that holds the image copies, on the uploads volume."""
    return Path(os.getenv("UPLOAD_DIR", "/app/uploads")) / "osrsclans"


def public_api_url() -> str:
    """Return the address browsers and Discord reach the API at.

    Raises `RuntimeError` when `PUBLIC_API_URL` is unset, because every image
    link would point nowhere.
    """
    url = os.getenv("PUBLIC_API_URL", "").rstrip("/")
    if not url:
        raise RuntimeError("PUBLIC_API_URL is not set")
    return url


@dataclass(frozen=True)
class ImageAsk:
    """One OSRSClans image: its kind, id, format, and the scale or frame asked."""

    kind: ImageKind
    image_id: int
    fmt: ImageFormat = "webp"
    scale: str | None = None
    frame: int | None = None

    def params(self) -> dict[str, str]:
        """Return the query string of the image, without the unset values."""
        pairs = {"scale": self.scale, "frame": self.frame}
        return {k: str(v) for k, v in sorted(pairs.items()) if v is not None}

    def upstream_path(self) -> str:
        """Return the OSRSClans route of the image."""
        return f"/osrs/{self.kind}/{self.image_id}.{self.fmt}"

    def cache_file(self) -> Path:
        """Return the file that holds this image's copy, one per id, format and size."""
        suffix = "".join(f"-{k[0]}{v}" for k, v in self.params().items())
        name = f"{self.image_id}{suffix}.{self.fmt}"
        return image_cache_dir() / self.kind / name


def osrs_image_url(ask: ImageAsk) -> str:
    """Return the Foundry address of an OSRSClans image."""
    query = urlencode(ask.params())
    route = f"/reference/osrs/images/{ask.kind}/{ask.image_id}.{ask.fmt}"
    return f"{public_api_url()}{route}{'?' + query if query else ''}"


def _store(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".part")
    partial.write_bytes(data)
    partial.replace(path)


def _read(path: Path) -> bytes | None:
    return path.read_bytes() if path.is_file() else None


async def cached_image(valkey: Valkey, ask: ImageAsk) -> bytes:
    """Return the image bytes, from the disk copy when one exists.

    Raises `OsrsClansNotFoundError` for an image OSRSClans does not have.
    """
    path = ask.cache_file()
    stored = await asyncio.to_thread(_read, path)
    if stored is not None:
        return stored
    missing_key = f"{_MISSING_PREFIX}{path.name}:{ask.kind}"
    if await valkey.get(missing_key):
        raise OsrsClansNotFoundError(f"OSRSClans has no {ask.upstream_path()}")
    try:
        resp = await guarded_get(
            valkey, f"image:{path}", ask.upstream_path(), ask.params()
        )
    except OsrsClansNotFoundError:
        await valkey.set(missing_key, "1", ex=_MISSING_TTL_SECONDS)
        raise
    if not resp.headers.get("content-type", "").startswith("image/"):
        raise OsrsClansError(f"OSRSClans sent no image for {ask.upstream_path()}")
    await asyncio.to_thread(_store, path, resp.content)
    return resp.content
