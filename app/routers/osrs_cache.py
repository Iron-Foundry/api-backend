"""Read-only proxy to the internal osrs-cache-service (items/npcs/objects/sprites)."""

from __future__ import annotations

import os
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.responses import Response

from app.docs import responses

router = APIRouter(
    prefix="/osrs-cache", tags=["osrs-cache"], responses=responses.PROXIED
)

OSRS_CACHE_SERVICE_URL = os.getenv(
    "OSRS_CACHE_SERVICE_URL", "http://osrs-cache-service:8100"
)

# Public base the browser reaches map tiles at. In production Traefik routes
# api.<domain>/map/* to the cache-tiles nginx sidecar; in dev the cache service
# is exposed directly. The manifest's relative tileUrl is rewritten onto this.
MAP_TILES_BASE_URL = os.getenv("MAP_TILES_BASE_URL", "").rstrip("/")

# Public immutable image assets, fetched cross-origin (blob download, canvas,
# previews, embeds). Match the cache-tiles nginx sidecar and the CDNs these
# replaced by serving them with a wildcard CORS header.
_IMMUTABLE_IMAGE_HEADERS = {
    "Cache-Control": "public, max-age=31536000, immutable",
    "Access-Control-Allow-Origin": "*",
}
_RENDER_IMAGE_HEADERS = {
    "Cache-Control": "no-store",
    "Access-Control-Allow-Origin": "*",
}

SearchQuery = Annotated[str | None, Query()]
LimitQuery = Annotated[int, Query(ge=1, le=500)]
OffsetQuery = Annotated[int, Query(ge=0)]


async def _proxy_json(path: str, params: dict[str, Any]) -> Any:
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{OSRS_CACHE_SERVICE_URL}{path}", params=params)
        except httpx.RequestError as exc:
            raise HTTPException(502, "OSRS cache service unavailable") from exc
    if resp.status_code != 200:
        raise HTTPException(resp.status_code, resp.text)
    return resp.json()


@router.get("/meta")
async def get_meta() -> dict[str, Any]:
    """Report the ingested cache build and how many definitions it holds."""
    return await _proxy_json("/meta", {})


@router.get("/items")
async def list_items(
    search: SearchQuery = None,
    limit: LimitQuery = 50,
    offset: OffsetQuery = 0,
) -> list[Any]:
    """Search item definitions by name, or page through all of them."""
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if search:
        params["search"] = search
    return await _proxy_json("/items", params)


@router.get("/items/names")
async def list_item_names() -> dict[str, Any]:
    """Return the full item id to name map, for bulk client-side lookups."""
    return await _proxy_json("/items/names", {})


@router.get("/items/{item_id}")
async def get_item(item_id: Annotated[int, Path(ge=0)]) -> dict[str, Any]:
    """Return one item definition, including its 2D render recipe."""
    return await _proxy_json(f"/items/{item_id}", {})


@router.get("/items/{item_id}/variants")
async def get_item_variants(item_id: Annotated[int, Path(ge=0)]) -> list[Any]:
    """List the noted, placeholder, and charged forms sharing this item's name."""
    return await _proxy_json(f"/items/{item_id}/variants", {})


@router.get("/npcs")
async def list_npcs(
    search: SearchQuery = None,
    limit: LimitQuery = 50,
    offset: OffsetQuery = 0,
) -> list[Any]:
    """Search NPC definitions by name, or page through all of them."""
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if search:
        params["search"] = search
    return await _proxy_json("/npcs", params)


@router.get("/objects")
async def list_objects(
    search: SearchQuery = None,
    limit: LimitQuery = 50,
    offset: OffsetQuery = 0,
) -> list[Any]:
    """Search scenery object definitions by name, or page through all of them."""
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if search:
        params["search"] = search
    return await _proxy_json("/objects", params)


@router.get("/item-icons/{item_id}")
async def get_item_icon(item_id: Annotated[int, Path(ge=0)]) -> Response:
    """Serve the baked 512px item icon as lossless WebP, immutably cached."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{OSRS_CACHE_SERVICE_URL}/item-icons/{item_id}")
        except httpx.RequestError as exc:
            raise HTTPException(502, "OSRS cache service unavailable") from exc
    if resp.status_code != 200:
        raise HTTPException(resp.status_code, "Item icon not found")
    return Response(
        content=resp.content,
        media_type="image/webp",
        headers=_IMMUTABLE_IMAGE_HEADERS,
    )


@router.get("/item-icons/{item_id}/render")
async def render_item_icon(
    item_id: Annotated[int, Path(ge=0)],
    size: Annotated[int, Query(ge=32, le=4096)] = 512,
) -> Response:
    """Render the item icon at a custom size on demand.

    Slower than the baked icon and cached for days rather than forever; prefer
    `/item-icons/{item_id}` unless you need a specific size.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(
                f"{OSRS_CACHE_SERVICE_URL}/item-icons/{item_id}/render",
                params={"size": size},
            )
        except httpx.RequestError as exc:
            raise HTTPException(502, "OSRS cache service unavailable") from exc
    if resp.status_code != 200:
        raise HTTPException(resp.status_code, "Item icon render not available")
    return Response(
        content=resp.content,
        media_type="image/webp",
        headers=_RENDER_IMAGE_HEADERS,
    )


@router.get("/sprites")
async def list_sprites(
    category: Annotated[str | None, Query()] = None,
    search: SearchQuery = None,
    limit: LimitQuery = 100,
    offset: OffsetQuery = 0,
) -> list[Any]:
    """Search UI sprites by name or category, or page through all of them."""
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if category:
        params["category"] = category
    if search:
        params["search"] = search
    return await _proxy_json("/sprites", params)


@router.get("/sprites/categories")
async def list_sprite_categories() -> list[Any]:
    """List the sprite category names, as grouped by RuneLite's SpriteID."""
    return await _proxy_json("/sprites/categories", {})


@router.get("/sprites/{sprite_id}")
async def get_sprite(sprite_id: Annotated[int, Path(ge=0)]) -> list[Any]:
    """List the frames in a sprite group. Most groups hold exactly one."""
    return await _proxy_json(f"/sprites/{sprite_id}", {})


@router.get("/sprites/{sprite_id}/{frame_index}")
async def get_sprite_image(
    sprite_id: Annotated[int, Path(ge=0)],
    frame_index: Annotated[int, Path(ge=0)],
    format: Annotated[str, Query(pattern="^(png|webp)$")] = "png",
    scale: Annotated[int | None, Query(ge=1, le=32)] = None,
) -> Response:
    """Serve one sprite frame as PNG or WebP, optionally scaled up."""
    params: dict[str, Any] = {"format": format}
    if scale is not None:
        params["scale"] = scale
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{OSRS_CACHE_SERVICE_URL}/sprites/{sprite_id}/{frame_index}",
                params=params,
            )
        except httpx.RequestError as exc:
            raise HTTPException(502, "OSRS cache service unavailable") from exc
    if resp.status_code != 200:
        raise HTTPException(resp.status_code, resp.text or "Sprite not found")
    media_type = "image/png" if format == "png" else "image/webp"
    return Response(
        content=resp.content,
        media_type=media_type,
        headers=_IMMUTABLE_IMAGE_HEADERS,
    )


@router.get("/map/meta")
async def get_map_meta() -> dict[str, Any]:
    """Return the slippy-map manifest: zoom range, bounds, and coverage bitmap.

    The relative `tileUrl` is rewritten onto the public tile host, so clients
    can use it directly.
    """
    manifest = await _proxy_json("/map/meta", {})
    if isinstance(manifest, dict) and MAP_TILES_BASE_URL and manifest.get("tileUrl"):
        manifest["tileUrl"] = f"{MAP_TILES_BASE_URL}{manifest['tileUrl']}"
    return manifest


@router.get("/map/regions/{region_id}")
async def get_map_region(region_id: Annotated[int, Path(ge=0)]) -> dict[str, Any]:
    """Return one map region's decoded terrain, keyed by region id."""
    return await _proxy_json(f"/map/regions/{region_id}", {})


@router.get("/map/locations")
async def get_map_locations(
    object_id: Annotated[int | None, Query(ge=0)] = None,
    plane: Annotated[int | None, Query(ge=0, le=3)] = None,
    min_x: Annotated[int | None, Query(ge=0)] = None,
    min_y: Annotated[int | None, Query(ge=0)] = None,
    max_x: Annotated[int | None, Query(ge=0)] = None,
    max_y: Annotated[int | None, Query(ge=0)] = None,
    limit: Annotated[int, Query(ge=1, le=10000)] = 1000,
) -> dict[str, Any]:
    """Find placed scenery, either by object id or within a tile bounding box."""
    params: dict[str, Any] = {"limit": limit}
    params.update(
        {
            key: value
            for key, value in (
                ("object_id", object_id),
                ("plane", plane),
                ("min_x", min_x),
                ("min_y", min_y),
                ("max_x", max_x),
                ("max_y", max_y),
            )
            if value is not None
        }
    )
    return await _proxy_json("/map/locations", params)


@router.get("/map/icons")
async def get_map_icons(
    plane: Annotated[int | None, Query(ge=0, le=4)] = None,
) -> dict[str, Any]:
    """List the map icons placed on a plane, joined to their source object."""
    params = {"plane": plane} if plane is not None else {}
    return await _proxy_json("/map/icons", params)


@router.get("/map/labels")
async def get_map_labels(
    plane: Annotated[int | None, Query(ge=0, le=3)] = None,
) -> dict[str, Any]:
    """List named areas on a plane. Areas carry no polygon, so these are unplaced."""
    params = {"plane": plane} if plane is not None else {}
    return await _proxy_json("/map/labels", params)


@router.get("/map/sections")
async def get_map_sections() -> dict[str, Any]:
    """List the named map sections used to jump the viewport to a landmark."""
    return await _proxy_json("/map/sections", {})
