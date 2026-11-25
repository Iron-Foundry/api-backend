"""The OSRSClans answer cache, exercised against a real Valkey."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
from pydantic import BaseModel
from valkey.asyncio import Valkey

from app.services.osrsclans import client
from app.services.osrsclans.art import (
    NpcSearchAsk,
    SpriteSearchAsk,
    cached_npcs,
    cached_sprites,
)
from app.services.osrsclans.client import CACHE_TTL_SECONDS, OsrsClansAsk, cache_key
from app.services.osrsclans.loot_rates import (
    LootRateAsk,
    LootSourceAsk,
    cached_loot_rates,
    cached_loot_sources,
)

pytestmark = pytest.mark.integration

_PAGE = {"items": [], "total": 0, "limit": 50, "offset": 0}
_NPC_PAGE = {
    "items": [{"id": 2042, "name": "Zulrah", "combatLevel": 725}],
    "total": 1,
    "limit": 20,
    "offset": 0,
}


@pytest.mark.parametrize(
    ("ask", "cached", "answer"),
    [
        (LootRateAsk(q="Vorkath"), cached_loot_rates, _PAGE),
        (LootSourceAsk(q="Vorkath"), cached_loot_sources, _PAGE),
        (NpcSearchAsk(q="Zulrah"), cached_npcs, _NPC_PAGE),
        (SpriteSearchAsk(q="Slayer"), cached_sprites, _PAGE),
    ],
)
async def test_second_ask_is_served_from_valkey(
    _env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    ask: OsrsClansAsk,
    cached: Callable[[Valkey, Any], Awaitable[BaseModel]],
    answer: dict[str, Any],
) -> None:
    fetched: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        fetched.append(request)
        return httpx.Response(200, json=answer)

    monkeypatch.setattr(client, "_transport", httpx.MockTransport(handle))
    valkey = Valkey.from_url(_env["valkey_uri"])
    try:
        await valkey.delete(cache_key(ask))
        first = await cached(valkey, ask)
        second = await cached(valkey, ask)
        ttl = await valkey.ttl(cache_key(ask))
    finally:
        await valkey.delete(cache_key(ask))
        await valkey.aclose()

    assert (first, len(fetched)) == (second, 1)
    assert 0 < ttl <= CACHE_TTL_SECONDS
