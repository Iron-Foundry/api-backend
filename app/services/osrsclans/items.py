"""The OSRSClans item queries: a window, a name search, one item, and every name.

The browser loads an item image from Foundry's image route, which keeps a copy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from pydantic import Field, RootModel
from valkey.asyncio import Valkey

from app.services.osrsclans.client import cached_page
from app.services.osrsclans.image_asks import ImageAsk
from app.services.osrsclans.images import osrs_image_url
from app.services.osrsclans.wire_model import OsrsClansModel


def item_image_url(item_id: int) -> str:
    """Return the Foundry address of an item's OSRSClans image at its largest size."""
    return osrs_image_url(ImageAsk("items", item_id))


class StackForm(OsrsClansModel):
    """The item a stack of `amount` or more shows as, such as a pile of coins."""

    amount: int
    item_id: int


class OsrsItem(OsrsClansModel):
    """One item definition. A noted or placeholder form has no name of its own."""

    id: int
    name: str | None
    examine: str | None = None
    stackable: bool = False
    value: int = 0
    members: bool = False
    tradeable: bool = False
    weight: int | None = None
    team_id: int | None = None
    noted_id: int | None = None
    placeholder_id: int | None = None
    stack_forms: list[StackForm] = Field(default_factory=list)


class OsrsItemPage(OsrsClansModel):
    items: list[OsrsItem]
    total: int
    limit: int
    offset: int


class ItemNames(RootModel[dict[str, str]]):
    """Every item's name, by its id."""


@dataclass(frozen=True)
class ItemWindowAsk:
    """One `/osrs/items` query: a window of items in id order."""

    path: ClassVar[str] = "/osrs/items"

    limit: int = 50
    offset: int = 0


@dataclass(frozen=True)
class ItemSearchAsk:
    """One `/osrs/items/search` query: items whose name holds `q`."""

    path: ClassVar[str] = "/osrs/items/search"

    q: str
    limit: int = 20
    offset: int = 0


@dataclass(frozen=True)
class ItemAsk:
    """One `/osrs/items/{item_id}` query."""

    path: ClassVar[str] = "/osrs/items/{item_id}"

    item_id: int


@dataclass(frozen=True)
class ItemNamesAsk:
    """The one `/osrs/items/names` query."""

    path: ClassVar[str] = "/osrs/items/names"


async def cached_items(
    valkey: Valkey, ask: ItemWindowAsk | ItemSearchAsk
) -> OsrsItemPage:
    """Return one window of items, from the cache when a copy is current."""
    return await cached_page(valkey, ask, OsrsItemPage)


async def cached_item(valkey: Valkey, item_id: int) -> OsrsItem:
    """Return one item. Raises `OsrsClansNotFoundError` for an id the game lacks."""
    return await cached_page(valkey, ItemAsk(item_id), OsrsItem)


async def cached_item_names(valkey: Valkey) -> ItemNames:
    """Return every item's name by id, from the cache when a copy is current."""
    return await cached_page(valkey, ItemNamesAsk(), ItemNames)
