"""Name indexes of every OSRS item, NPC and sprite, for fuzzy name search.

Each index loads from OSRSClans' bulk lists (`/osrs/items/names`,
`/osrs/npcs/names`, and `/osrs/sprites` in windows of 500) through `cached_page`.
`NameIndexService` builds all three when the API starts and rebuilds them in the
background while the site runs, so a search reads a ready index and never waits
for OSRSClans. A search builds an index itself only when none exists yet, and
concurrent searches share that one build.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, ClassVar

from pydantic import RootModel
from valkey.asyncio import Valkey

from app.services.osrsclans.art import OsrsSprite, SpriteWindowAsk, cached_sprites
from app.services.osrsclans.client import CACHE_TTL_SECONDS, cached_page
from app.services.osrsclans.items import cached_item_names
from app.services.osrsclans.name_search import NameEntry, name_entries

_SPRITE_WINDOW = 500
# A search rebuilds an index this old itself; the service normally keeps it fresher.
_MAX_AGE_SECONDS = 2 * CACHE_TTL_SECONDS
_built: dict[str, tuple[float, Any]] = {}
_building: dict[str, asyncio.Task[Any]] = {}


class NpcNames(RootModel[dict[str, str]]):
    """Every NPC's name, by its id."""


@dataclass(frozen=True)
class NpcNamesAsk:
    """The one `/osrs/npcs/names` query."""

    path: ClassVar[str] = "/osrs/npcs/names"


@dataclass(frozen=True)
class SpriteIndex:
    """The sprite name entries, and each sprite by its id."""

    entries: list[NameEntry]
    sprites: dict[int, OsrsSprite]


def _finish(kind: str, task: asyncio.Task[Any]) -> None:
    if _building.get(kind) is task:
        del _building[kind]
    if not task.cancelled():
        task.exception()


async def _build_shared[T](kind: str, build: Callable[[], Awaitable[T]]) -> T:
    task = _building.get(kind)
    # A task belongs to one event loop; a second app on another loop builds its own.
    if task is None or task.get_loop() is not asyncio.get_running_loop():

        async def run() -> T:
            value = await build()
            _built[kind] = (time.monotonic(), value)
            return value

        task = asyncio.create_task(run())
        _building[kind] = task
        task.add_done_callback(lambda done: _finish(kind, done))
    return await asyncio.shield(task)


async def _kept[T](kind: str, build: Callable[[], Awaitable[T]], now: float) -> T:
    hit = _built.get(kind)
    if hit is not None and now - hit[0] < _MAX_AGE_SECONDS:
        return hit[1]
    return await _build_shared(kind, build)


def _pairs(names: dict[str, str]) -> list[tuple[int, str]]:
    return [(int(k), v) for k, v in names.items()]


async def _npc_entries(valkey: Valkey) -> list[NameEntry]:
    names = await cached_page(valkey, NpcNamesAsk(), NpcNames)
    return name_entries(_pairs(names.root))


async def _item_entries(valkey: Valkey) -> list[NameEntry]:
    return name_entries(_pairs((await cached_item_names(valkey)).root))


async def _sprite_entries(valkey: Valkey) -> SpriteIndex:
    sprites: list[OsrsSprite] = []
    offset = 0
    while True:
        page = await cached_sprites(valkey, SpriteWindowAsk(_SPRITE_WINDOW, offset))
        sprites.extend(page.items)
        offset += _SPRITE_WINDOW
        if not page.items or offset >= page.total:
            break
    entries = name_entries((s.id, s.name) for s in sprites)
    return SpriteIndex(entries, {s.id: s for s in sprites})


async def npc_index(valkey: Valkey, now: float | None = None) -> list[NameEntry]:
    """Return the name index of every NPC."""
    clock = now if now is not None else time.monotonic()
    return await _kept("npcs", lambda: _npc_entries(valkey), clock)


async def item_index(valkey: Valkey, now: float | None = None) -> list[NameEntry]:
    """Return the name index of every named item."""
    clock = now if now is not None else time.monotonic()
    return await _kept("items", lambda: _item_entries(valkey), clock)


async def sprite_index(valkey: Valkey, now: float | None = None) -> SpriteIndex:
    """Return the name index of every sprite, with each sprite by id."""
    clock = now if now is not None else time.monotonic()
    return await _kept("sprites", lambda: _sprite_entries(valkey), clock)


async def refresh_name_indexes(valkey: Valkey) -> dict[str, int]:
    """Rebuild all three indexes and return their sizes; searches keep the old ones meanwhile."""
    npcs = await _build_shared("npcs", lambda: _npc_entries(valkey))
    items = await _build_shared("items", lambda: _item_entries(valkey))
    sprites = await _build_shared("sprites", lambda: _sprite_entries(valkey))
    return {"npcs": len(npcs), "items": len(items), "sprites": len(sprites.entries)}


def forget_indexes() -> None:
    """Drop every built index, so the next search rebuilds it."""
    _built.clear()
