"""The OSRSClans NPC and sprite name searches, and the image each result links to.

A frenzy card takes its image from one of these results. The browser loads the
image from OSRSClans itself, which sends CORS `*` on its image routes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from pydantic import computed_field
from valkey.asyncio import Valkey

from app.services.osrsclans.client import OSRSCLANS_API_URL, cached_page
from app.services.osrsclans.wire_model import OsrsClansModel


class OsrsNpc(OsrsClansModel):
    """One NPC definition. Some ids have no still, and their image answers 404."""

    id: int
    name: str
    combat_level: int | None = None

    @computed_field
    @property
    def image_url(self) -> str:
        return f"{OSRSCLANS_API_URL}/osrs/npcs/{self.id}.webp"


class OsrsSprite(OsrsClansModel):
    """One sprite of the game interface, such as a skill icon."""

    id: int
    name: str
    category: str | None = None

    @computed_field
    @property
    def image_url(self) -> str:
        return f"{OSRSCLANS_API_URL}/osrs/sprites/{self.id}.webp"


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


async def cached_npcs(valkey: Valkey, ask: NpcSearchAsk) -> OsrsNpcPage:
    """Return one window of NPCs, from the cache when a copy is current."""
    return await cached_page(valkey, ask, OsrsNpcPage)


async def cached_sprites(valkey: Valkey, ask: SpriteSearchAsk) -> OsrsSpritePage:
    """Return one window of sprites, from the cache when a copy is current."""
    return await cached_page(valkey, ask, OsrsSpritePage)
