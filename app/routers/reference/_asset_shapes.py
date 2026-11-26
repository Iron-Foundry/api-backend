"""The asset manager's item and sprite shapes, built from OSRSClans answers."""

from __future__ import annotations

from pydantic import BaseModel

from app.services.osrsclans.art import OsrsSprite
from app.services.osrsclans.images import ImageAsk, osrs_image_url
from app.services.osrsclans.items import OsrsItem, item_image_url


class ItemOut(BaseModel):
    item_id: int
    name: str
    examine: str | None
    stackable: bool
    value: int
    members: bool
    tradeable: bool
    noted_id: int | None
    placeholder_id: int | None
    team_id: int | None
    weight: int | None
    icon_url: str
    variant_count: int


class SpriteFrameOut(BaseModel):
    sprite_id: int
    frame_index: int
    width: int
    height: int
    webp_url: str
    svg_url: str
    name: str
    category: str | None


class SpriteFramePage(BaseModel):
    """The frames of one window of sprites. `sprites` is the window's sprite count."""

    items: list[SpriteFrameOut]
    sprites: int


class SpriteCategoryOut(BaseModel):
    category: str
    count: int


def item_out(item: OsrsItem, name: str | None = None) -> ItemOut:
    """Return the asset shape of an item. `name` stands in for a form with none."""
    return ItemOut(
        item_id=item.id,
        name=name or item.name or f"Item {item.id}",
        examine=item.examine,
        stackable=item.stackable,
        value=item.value,
        members=item.members,
        tradeable=item.tradeable,
        noted_id=item.noted_id,
        placeholder_id=item.placeholder_id,
        team_id=item.team_id,
        weight=item.weight,
        icon_url=item_image_url(item.id),
        variant_count=1 + len(variant_forms(item)),
    )


def variant_forms(item: OsrsItem) -> list[tuple[int, str]]:
    """Return the id and name of each other form of a named item."""
    base = item.name or f"Item {item.id}"
    forms = [
        (item.noted_id, f"{base} (noted)"),
        (item.placeholder_id, f"{base} (placeholder)"),
    ]
    named = [(form_id, name) for form_id, name in forms if form_id is not None]
    stacks = [(s.item_id, f"{base} x{s.amount:,}") for s in item.stack_forms]
    return named + stacks


def variants_out(item: OsrsItem) -> list[ItemOut]:
    """Return an item and each of its other forms, the forms named after it."""
    bare = {"stack_forms": [], "noted_id": None, "placeholder_id": None}
    forms = [
        item_out(item.model_copy(update={"id": form_id, **bare}), name)
        for form_id, name in variant_forms(item)
    ]
    return [item_out(item), *forms]


def frames_out(sprite: OsrsSprite) -> list[SpriteFrameOut]:
    """Return one asset row per non-empty frame of a sprite."""
    return [
        SpriteFrameOut(
            sprite_id=sprite.id,
            frame_index=frame.frame,
            width=frame.width,
            height=frame.height,
            webp_url=osrs_image_url(ImageAsk("sprites", sprite.id, frame=frame.frame)),
            svg_url=osrs_image_url(
                ImageAsk("sprites", sprite.id, "svg", frame=frame.frame)
            ),
            name=sprite.name,
            category=sprite.category,
        )
        for frame in sprite.frames
        if not frame.empty
    ]
