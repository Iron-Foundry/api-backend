"""The OSRSClans NPC and sprite name searches, and the image each result links to.

A frenzy card takes its image from one of these results. The browser loads the
image from OSRSClans itself, which sends CORS `*` on its image routes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from pydantic import Field, RootModel, computed_field
from valkey.asyncio import Valkey

from app.services.osrsclans.client import cached_page
from app.services.osrsclans.images import ImageAsk, osrs_image_url
from app.services.osrsclans.wire_model import OsrsClansModel


class OsrsNpc(OsrsClansModel):
    """One NPC definition. Some ids have no still, and their image answers 404."""

    id: int
    name: str
    combat_level: int | None = None

    @computed_field
    @property
    def image_url(self) -> str:
        return osrs_image_url(ImageAsk("npcs", self.id))


class SpriteFrame(OsrsClansModel):
    """One frame of a sprite. Most sprites have one."""

    frame: int
    width: int
    height: int
    empty: bool = False


class OsrsSprite(OsrsClansModel):
    """One sprite of the game interface, such as a skill icon."""

    id: int
    name: str
    category: str | None = None
    frames: list[SpriteFrame] = Field(default_factory=list)

    @computed_field
    @property
    def image_url(self) -> str:
        return osrs_image_url(ImageAsk("sprites", self.id))


class OsrsNpcPage(OsrsClansModel):
    items: list[OsrsNpc]
    total: int
    limit: int
    offset: int


class OsrsSpritePage(OsrsClansModel):
    items: list[OsrsSprite]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class NpcSearchAsk:
    """One `/osrs/npcs/search` query: NPCs whose name holds `q`."""

    path: ClassVar[str] = "/osrs/npcs/search"

    q: str
    limit: int = 20
    offset: int = 0


@dataclass(frozen=True)
class SpriteSearchAsk:
    """One `/osrs/sprites/search` query: sprites whose name holds `q`."""

    path: ClassVar[str] = "/osrs/sprites/search"

    q: str
    limit: int = 20
    offset: int = 0
    category: str | None = None


@dataclass(frozen=True)
class SpriteWindowAsk:
    """One `/osrs/sprites` query: a window of sprites in id order."""

    path: ClassVar[str] = "/osrs/sprites"

    limit: int = 50
    offset: int = 0
    category: str | None = None


@dataclass(frozen=True)
class SpriteAsk:
    """One `/osrs/sprites/{sprite_id}` query."""

    path: ClassVar[str] = "/osrs/sprites/{sprite_id}"

    sprite_id: int


@dataclass(frozen=True)
class SpriteCategoriesAsk:
    """The one `/osrs/sprites/categories` query."""

    path: ClassVar[str] = "/osrs/sprites/categories"


class SpriteCategory(OsrsClansModel):
    """A sprite category and its sprite count. Null groups the uncategorised."""

    category: str | None
    sprites: int


class SpriteCategories(RootModel[list[SpriteCategory]]):
    """Every sprite category."""


async def cached_npcs(valkey: Valkey, ask: NpcSearchAsk) -> OsrsNpcPage:
    """Return one window of NPCs, from the cache when a copy is current."""
    return await cached_page(valkey, ask, OsrsNpcPage)


async def cached_sprites(
    valkey: Valkey, ask: SpriteSearchAsk | SpriteWindowAsk
) -> OsrsSpritePage:
    """Return one window of sprites, from the cache when a copy is current."""
    return await cached_page(valkey, ask, OsrsSpritePage)


async def cached_sprite(valkey: Valkey, sprite_id: int) -> OsrsSprite:
    """Return one sprite. Raises `OsrsClansNotFoundError` for an id the game lacks."""
    return await cached_page(valkey, SpriteAsk(sprite_id), OsrsSprite)


async def cached_sprite_categories(valkey: Valkey) -> SpriteCategories:
    """Return every sprite category, from the cache when a copy is current."""
    return await cached_page(valkey, SpriteCategoriesAsk(), SpriteCategories)
