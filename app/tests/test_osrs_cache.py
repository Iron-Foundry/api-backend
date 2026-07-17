"""Tests for the read-only osrs-cache-service proxy router.

Mocks replace the `httpx` name inside `app.routers.osrs_cache`'s own module
namespace, not the shared `httpx` module object - the test client itself is
also an `httpx.AsyncClient` wrapping an ASGITransport, so patching the real
class would hijack its own request to the test app along with the outbound
proxy call.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from httpx import AsyncClient, Response

from app.routers import osrs_cache


def _fake_client(response: Response | MagicMock) -> MagicMock:
    fake = MagicMock()
    fake.__aenter__ = AsyncMock(return_value=fake)
    fake.__aexit__ = AsyncMock(return_value=False)
    fake.get = AsyncMock(return_value=response)
    return fake


def _fake_httpx_module(fake_client: MagicMock) -> MagicMock:
    fake = MagicMock()
    fake.AsyncClient = MagicMock(return_value=fake_client)
    fake.RequestError = httpx.RequestError
    return fake


async def test_render_item_icon_proxies_size_and_content(
    anon_client: AsyncClient,
) -> None:
    fake_client = _fake_client(Response(200, content=b"webp-bytes"))
    with patch.object(osrs_cache, "httpx", _fake_httpx_module(fake_client)):
        resp = await anon_client.get("/osrs-cache/item-icons/995/render?size=1024")

    assert resp.status_code == 200
    assert resp.content == b"webp-bytes"
    assert resp.headers["cache-control"] == "no-store"
    assert resp.headers["access-control-allow-origin"] == "*"
    fake_client.get.assert_awaited_once()
    args, kwargs = fake_client.get.call_args
    assert args[0].endswith("/item-icons/995/render")
    assert kwargs["params"] == {"size": 1024}


async def test_list_item_names_proxies_map(anon_client: AsyncClient) -> None:
    fake_client = _fake_client(
        Response(200, json={"995": "Coins", "4151": "Abyssal whip"})
    )
    with patch.object(osrs_cache, "httpx", _fake_httpx_module(fake_client)):
        resp = await anon_client.get("/osrs-cache/items/names")

    assert resp.status_code == 200
    assert resp.json() == {"995": "Coins", "4151": "Abyssal whip"}
    args, _ = fake_client.get.call_args
    assert args[0].endswith("/items/names")


async def test_render_item_icon_rejects_size_out_of_range(
    anon_client: AsyncClient,
) -> None:
    resp = await anon_client.get("/osrs-cache/item-icons/995/render?size=8192")
    assert resp.status_code == 422


async def test_render_item_icon_not_found_upstream(anon_client: AsyncClient) -> None:
    upstream = MagicMock()
    upstream.status_code = 404
    fake_client = _fake_client(upstream)
    with patch.object(osrs_cache, "httpx", _fake_httpx_module(fake_client)):
        resp = await anon_client.get("/osrs-cache/item-icons/995/render")

    assert resp.status_code == 404


async def test_get_sprite_image_proxies_scale(anon_client: AsyncClient) -> None:
    fake_client = _fake_client(Response(200, content=b"webp-bytes"))
    with patch.object(osrs_cache, "httpx", _fake_httpx_module(fake_client)):
        resp = await anon_client.get("/osrs-cache/sprites/1234/0?format=webp&scale=4")

    assert resp.status_code == 200
    assert resp.content == b"webp-bytes"
    assert resp.headers["cache-control"] == "public, max-age=31536000, immutable"
    args, kwargs = fake_client.get.call_args
    assert args[0].endswith("/sprites/1234/0")
    assert kwargs["params"] == {"format": "webp", "scale": 4}


async def test_get_sprite_image_rejects_scale_out_of_range(
    anon_client: AsyncClient,
) -> None:
    resp = await anon_client.get("/osrs-cache/sprites/1234/0?scale=64")
    assert resp.status_code == 422
