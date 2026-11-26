"""One OSRSClans image ask, and the per-kind values OSRSClans serves."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ImageKind = Literal["items", "npcs", "sprites"]
ImageFormat = Literal["webp", "svg"]
# The values OSRSClans serves (its ItemScale, SpriteScale and ImageFormat). Each
# kind's default scale and frame 0 map to "unset", so one image is one copy.
_FORMATS: dict[str, frozenset[str]] = {
    "items": frozenset({"webp", "svg"}),
    "sprites": frozenset({"webp", "svg"}),
    "npcs": frozenset({"webp"}),
}
_SCALES: dict[str, frozenset[str]] = {
    "items": frozenset({"1", "2", "4", "8", "max"}),
    "sprites": frozenset({"1", "2", "4", "8", "16", "max"}),
    "npcs": frozenset(),
}
_DEFAULT_SCALES = {"items": "max", "sprites": "1"}


class InvalidImageAskError(ValueError):
    """The format, scale or frame does not fit the image kind."""


def image_cache_dir() -> Path:
    """Return the folder that holds the image copies, on the uploads volume."""
    return Path(os.getenv("UPLOAD_DIR", "/app/uploads")) / "osrsclans"


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


def checked_ask(
    kind: ImageKind,
    image_id: int,
    fmt: ImageFormat,
    scale: str | None,
    frame: int | None,
) -> ImageAsk:
    """Return the ask in its one stored form, or raise `InvalidImageAskError`.

    Only a sprite takes a frame, and an NPC takes no scale.
    """
    if fmt not in _FORMATS[kind]:
        raise InvalidImageAskError(f"{kind} have no {fmt} image")
    if scale is not None and scale not in _SCALES[kind]:
        raise InvalidImageAskError(f"{kind} have no scale {scale}")
    if frame is not None and kind != "sprites":
        raise InvalidImageAskError(f"{kind} have no frames")
    stored_scale = None if scale == _DEFAULT_SCALES.get(kind) else scale
    return ImageAsk(kind, image_id, fmt, stored_scale, frame or None)
