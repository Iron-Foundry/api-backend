"""A failed OSRSClans call pauses all calls, and identical calls share one request."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest
from httpx import AsyncClient

from app.services.osrsclans import client
from app.services.osrsclans.art import NpcSearchAsk, OsrsNpcPage
from app.services.osrsclans.cooldown import COOLDOWN_KEY

_PAGE = {
    "items": [{"id": 8059, "name": "Vorkath"}],
    "total": 1,
    "limit": 20,
    "offset": 0,
}
_ROUTE = "/reference/osrs/npcs?q=vorkath"


@pytest.mark.parametrize(
    ("status", "headers", "pause"),
    [
        (503, {"Retry-After": "45"}, 45),
        (429, {}, 30),
        (504, {"Retry-After": "9999"}, 300),
        (500, {}, None),
        (404, {}, None),
        (400, {}, None),
    ],
)
async def test_failure_starts_the_pause_it_calls_for(
    anon_client: AsyncClient,
    mock_valkey: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    headers: dict[str, str],
    pause: int | None,
) -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(status, headers=headers))
    monkeypatch.setattr(client, "_transport", transport)

    assert (await anon_client.get(_ROUTE)).status_code == 502
    pauses = [c for c in mock_valkey.set.await_args_list if c.args[0] == COOLDOWN_KEY]
    assert [c.kwargs["ex"] for c in pauses] == ([pause] if pause else [])


async def test_a_running_pause_answers_503_unsent(
    anon_client: AsyncClient, mock_valkey: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_PAGE)

    monkeypatch.setattr(client, "_transport", httpx.MockTransport(answer))
    mock_valkey.get.side_effect = lambda key: (
        b"99999999999" if key == COOLDOWN_KEY else None
    )

    resp = await anon_client.get(_ROUTE)

    assert resp.status_code == 503
    assert int(resp.headers["Retry-After"]) > 0
    assert seen == []


async def test_identical_calls_share_one_request(
    mock_valkey: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[httpx.Request] = []

    async def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        await asyncio.sleep(0.05)
        return httpx.Response(200, json=_PAGE)

    monkeypatch.setattr(client, "_transport", httpx.MockTransport(answer))
    ask = NpcSearchAsk("vorkath")

    pages = await asyncio.gather(
        *(client.cached_page(mock_valkey, ask, OsrsNpcPage) for _ in range(5))
    )

    assert len(seen) == 1
    assert {p.items[0].name for p in pages} == {"Vorkath"}
