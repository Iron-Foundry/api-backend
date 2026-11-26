"""The OSRS name indexes: one shared build, and a background refresh that survives failure."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from app.services.osrsclans import client, name_index_service
from app.services.osrsclans.client import OsrsClansError
from app.services.osrsclans.name_index import npc_index
from app.services.osrsclans.name_index_service import NameIndexService


async def test_concurrent_searches_share_one_build(
    mock_valkey: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[httpx.Request] = []

    async def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        await asyncio.sleep(0.05)
        return httpx.Response(200, json={"8059": "Vorkath"})

    monkeypatch.setattr(client, "_transport", httpx.MockTransport(answer))

    indexes = await asyncio.gather(*(npc_index(mock_valkey) for _ in range(5)))

    assert len(seen) == 1
    assert {idx[0].name for idx in indexes} == {"Vorkath"}


@pytest.mark.parametrize(
    ("outcome", "built"),
    [({"npcs": 1, "items": 2, "sprites": 3}, True), (OsrsClansError("down"), False)],
)
async def test_refresh_reports_whether_it_built(
    mock_valkey: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    outcome: dict[str, int] | Exception,
    built: bool,
) -> None:
    refresh = AsyncMock(side_effect=[outcome])
    monkeypatch.setattr(name_index_service, "refresh_name_indexes", refresh)

    assert await NameIndexService(mock_valkey)._refresh_once() is built
