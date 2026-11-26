from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from valkey.asyncio import Valkey

from app.dependencies import get_valkey
from app.docs import responses
from app.services.osrsclans.client import OsrsClansError, OsrsClansNotFoundError
from app.services.osrsclans.images import (
    MEDIA_TYPES,
    ImageAsk,
    ImageFormat,
    ImageKind,
    cached_image,
)

router = APIRouter(prefix="/osrs/images", responses=responses.PROXIED)

_WEEK_SECONDS = 7 * 24 * 3600
_BASE_HEADERS = {
    "Cache-Control": f"public, max-age={_WEEK_SECONDS}",
    "Access-Control-Allow-Origin": "*",
    "X-Content-Type-Options": "nosniff",
}
# An SVG opened on its own runs any script it holds, on the API's origin.
_SVG_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"
}


@router.get(
    "/{kind}/{image_id:int}.{fmt}",
    response_class=Response,
    responses={200: {"content": {"image/webp": {}, "image/svg+xml": {}}}},
)
async def get_osrs_image(
    kind: ImageKind,
    image_id: Annotated[int, Path(ge=0, le=16_777_215)],
    fmt: ImageFormat,
    valkey: Annotated[Valkey, Depends(get_valkey)],
    scale: Annotated[str | None, Query(pattern=r"^([0-9]{1,2}|max)$")] = None,
    frame: Annotated[int | None, Query(ge=0, le=4096)] = None,
) -> Response:
    """Return an OSRSClans item, NPC or sprite image, from Foundry's own copy.

    The first request for an image fetches it from OSRSClans and keeps a copy on
    disk; each later request reads the copy. `scale` and `frame` pass through to
    OSRSClans. Answers 404 for an image OSRSClans does not have, and 503 while
    OSRSClans cools down after a failure.
    """
    ask = ImageAsk(kind, image_id, fmt, scale, frame)
    try:
        data = await cached_image(valkey, ask)
    except OsrsClansNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OsrsClansError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    headers = _BASE_HEADERS | (_SVG_HEADERS if fmt == "svg" else {})
    return Response(content=data, media_type=MEDIA_TYPES[fmt], headers=headers)
