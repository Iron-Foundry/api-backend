"""Tile image processing: PNG -> WebP conversion, dominant colour, content detection."""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image

_RS_OFFSET_X = 960
_PY_CONST = 17600
_ALPHA_THRESHOLD = 128
_CONTENT_ALPHA_RATIO = 0.05


@dataclass
class ProcessedTile:
    data: bytes
    content_type: str
    size_bytes: int
    dominant_color: str | None
    has_content: bool


def process_tile(raw_png: bytes) -> ProcessedTile:
    """Convert a raw PNG tile to WebP and extract metadata."""
    img = Image.open(io.BytesIO(raw_png)).convert("RGBA")
    flat = img.tobytes()
    has_content = _check_has_content(flat)
    dominant_color = _dominant_color(flat) if has_content else None
    webp = _encode_webp(img)
    return ProcessedTile(
        data=webp,
        content_type="image/webp",
        size_bytes=len(webp),
        dominant_color=dominant_color,
        has_content=has_content,
    )


def tile_region_id(tx: int, ty_tms: int, z: int) -> int | None:
    """Compute the OSRS region ID for the top-left coordinate of a tile.

    Returns None for zoom levels below 6 where a single tile spans many regions.
    """
    if z < 6:
        return None
    tpi = 2 ** (14 - z)
    ty_xyz = 2**z - 1 - ty_tms
    osrs_x = tx * tpi + _RS_OFFSET_X
    osrs_y = _PY_CONST - ty_xyz * tpi
    return ((osrs_x // 64) << 8) | (osrs_y // 64)


def _check_has_content(flat: bytes) -> bool:
    total = len(flat) // 4
    opaque = sum(1 for i in range(3, len(flat), 4) if flat[i] > _ALPHA_THRESHOLD)
    return opaque / total > _CONTENT_ALPHA_RATIO


def _dominant_color(flat: bytes) -> str | None:
    opaque: list[tuple[int, int, int]] = [
        (flat[i], flat[i + 1], flat[i + 2])
        for i in range(0, len(flat), 4)
        if flat[i + 3] > _ALPHA_THRESHOLD
    ]
    if not opaque:
        return None
    n = len(opaque)
    r = sum(p[0] for p in opaque) // n
    g = sum(p[1] for p in opaque) // n
    b = sum(p[2] for p in opaque) // n
    return f"#{r:02x}{g:02x}{b:02x}"


def _encode_webp(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="WEBP", lossless=True, method=6)
    return buf.getvalue()
