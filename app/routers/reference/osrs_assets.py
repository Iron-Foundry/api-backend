from __future__ import annotations

from collections.abc import Awaitable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from valkey.asyncio import Valkey

from app.dependencies import get_valkey
from app.docs import responses
from app.services.osrsclans.art import (
    SpriteSearchAsk,
    SpriteWindowAsk,
    cached_sprite,
    cached_sprite_categories,
    cached_sprites,
)
from app.services.osrsclans.client import OsrsClansError, OsrsClansNotFoundError
from app.services.osrsclans.items import (
    ItemSearchAsk,
    ItemWindowAsk,
    cached_item,
    cached_item_names,
    cached_items,
)

from ._asset_shapes import (
    ItemOut,
    SpriteCategoryOut,
    SpriteFrameOut,
    SpriteFramePage,
    frames_out,
    item_out,
    variants_out,
)

router = APIRouter(prefix="/osrs", responses=responses.PROXIED)

ValkeyDep = Annotated[Valkey, Depends(get_valkey)]
IdPath = Annotated[int, Path(ge=0, le=16_777_215)]
SearchQuery = Annotated[str | None, Query(min_length=2, max_length=64)]
CategoryQuery = Annotated[str | None, Query(min_length=1, max_length=64)]
LimitQuery = Annotated[int, Query(ge=1, le=100)]
OffsetQuery = Annotated[int, Query(ge=0)]


def _bad_gateway(exc: OsrsClansError) -> HTTPException:
    return HTTPException(status_code=502, detail=str(exc))


@router.get("/items")
async def list_items(
    valkey: ValkeyDep,
    search: SearchQuery = None,
    limit: LimitQuery = 50,
    offset: OffsetQuery = 0,
) -> list[ItemOut]:
    """Return a window of named items from OSRSClans, or those whose name holds `search`."""
    ask = (
        ItemSearchAsk(search, limit, offset) if search else ItemWindowAsk(limit, offset)
    )
    try:
        page = await cached_items(valkey, ask)
    except OsrsClansError as exc:
        raise _bad_gateway(exc) from exc
    return [item_out(item) for item in page.items if item.name]


@router.get("/items/names")
async def item_names(valkey: ValkeyDep) -> dict[str, str]:
    """Return every item's name by id. Fetch it once a session, not per row."""
    try:
        return (await cached_item_names(valkey)).root
    except OsrsClansError as exc:
        raise _bad_gateway(exc) from exc


async def _found[T](lookup: Awaitable[T], missing: str) -> T:
    try:
        return await lookup
    except OsrsClansNotFoundError as exc:
        raise HTTPException(status_code=404, detail=missing) from exc
    except OsrsClansError as exc:
        raise _bad_gateway(exc) from exc


@router.get("/items/{item_id}")
async def get_item(item_id: IdPath, valkey: ValkeyDep) -> ItemOut:
    """Return one item."""
    return item_out(await _found(cached_item(valkey, item_id), "Item not found"))


@router.get("/items/{item_id}/variants")
async def item_variants(item_id: IdPath, valkey: ValkeyDep) -> list[ItemOut]:
    """Return an item with its noted, placeholder and stack forms."""
    item = await _found(cached_item(valkey, item_id), "Item not found")
    return variants_out(item)


@router.get("/sprites/categories")
async def sprite_categories(valkey: ValkeyDep) -> list[SpriteCategoryOut]:
    """Return every named sprite category with its sprite count."""
    try:
        categories = await cached_sprite_categories(valkey)
    except OsrsClansError as exc:
        raise _bad_gateway(exc) from exc
    return [
        SpriteCategoryOut(category=c.category, count=c.sprites)
        for c in categories.root
        if c.category
    ]


@router.get("/sprite-frames")
async def list_sprite_frames(
    valkey: ValkeyDep,
    search: SearchQuery = None,
    category: CategoryQuery = None,
    limit: LimitQuery = 50,
    offset: OffsetQuery = 0,
) -> SpriteFramePage:
    """Return a window of sprites as one row per frame, filtered by name or category.

    `limit` and `offset` count sprites, not frames. Advance `offset` by `sprites`.
    """
    ask = (
        SpriteSearchAsk(search, limit, offset, category)
        if search
        else SpriteWindowAsk(limit, offset, category)
    )
    try:
        page = await cached_sprites(valkey, ask)
    except OsrsClansError as exc:
        raise _bad_gateway(exc) from exc
    frames = [frame for sprite in page.items for frame in frames_out(sprite)]
    return SpriteFramePage(items=frames, sprites=len(page.items))


@router.get("/sprite-frames/{sprite_id}")
async def get_sprite_frames(
    sprite_id: IdPath, valkey: ValkeyDep
) -> list[SpriteFrameOut]:
    """Return each frame of one sprite."""
    sprite = await _found(cached_sprite(valkey, sprite_id), "Sprite not found")
    return frames_out(sprite)
