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
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from httpx import ASGITransport, AsyncClient, Response

from app.routers import osrs_cache

_FRONTEND_ORIGIN = "https://ironfoundry.cc"


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
    assert resp.headers["access-control-allow-origin"] == "*"
    args, _ = fake_client.get.call_args
    assert args[0].endswith("/items/names")


async def test_list_npc_names_proxies_map(anon_client: AsyncClient) -> None:
    fake_client = _fake_client(Response(200, json={"8": "Nechryael"}))
    with patch.object(osrs_cache, "httpx", _fake_httpx_module(fake_client)):
        resp = await anon_client.get("/osrs-cache/npcs/names")

    assert resp.status_code == 200
    assert resp.json() == {"8": "Nechryael"}
    assert resp.headers["access-control-allow-origin"] == "*"
    args, _ = fake_client.get.call_args
    assert args[0].endswith("/npcs/names")


async def test_json_routes_allow_any_origin(anon_client: AsyncClient) -> None:
    fake_client = _fake_client(Response(200, json={"build_id": 2024, "items": 17157}))
    with patch.object(osrs_cache, "httpx", _fake_httpx_module(fake_client)):
        resp = await anon_client.get(
            "/osrs-cache/meta", headers={"Origin": "https://osrsclans.cc"}
        )

    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "*"


async def test_frontend_origin_keeps_credentialed_cors() -> None:
    app = FastAPI()
    app.include_router(osrs_cache.router)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[_FRONTEND_ORIGIN],
        allow_credentials=True,
        allow_methods=["GET"],
        allow_headers=["Authorization", "Content-Type"],
    )
    fake_client = _fake_client(Response(200, json={"build_id": 2024}))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        with patch.object(osrs_cache, "httpx", _fake_httpx_module(fake_client)):
            resp = await client.get(
                "/osrs-cache/meta", headers={"Origin": _FRONTEND_ORIGIN}
            )

    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == _FRONTEND_ORIGIN
    assert resp.headers["access-control-allow-credentials"] == "true"


async def test_get_npc_proxies_definition(anon_client: AsyncClient) -> None:
    definition = {"npc_id": 8, "name": "Nechryael", "model_ids": [5074]}
    fake_client = _fake_client(Response(200, json=definition))
    with patch.object(osrs_cache, "httpx", _fake_httpx_module(fake_client)):
        resp = await anon_client.get("/osrs-cache/npcs/8")

    assert resp.status_code == 200
    assert resp.json() == definition
    args, _ = fake_client.get.call_args
    assert args[0].endswith("/npcs/8")


async def test_get_npc_not_found_upstream(anon_client: AsyncClient) -> None:
    fake_client = _fake_client(Response(404, text="NPC not found"))
    with patch.object(osrs_cache, "httpx", _fake_httpx_module(fake_client)):
        resp = await anon_client.get("/osrs-cache/npcs/999999")

    assert resp.status_code == 404


async def test_list_gamevals_proxies_namespace_and_search(
    anon_client: AsyncClient,
) -> None:
    fake_client = _fake_client(
        Response(200, json=[{"entry_id": 8, "name": "nechryael"}])
    )
    with patch.object(osrs_cache, "httpx", _fake_httpx_module(fake_client)):
        resp = await anon_client.get("/osrs-cache/gamevals?namespace=npcs&search=nech")

    assert resp.status_code == 200
    args, kwargs = fake_client.get.call_args
    assert args[0].endswith("/gamevals")
    assert kwargs["params"] == {
        "limit": 50,
        "offset": 0,
        "namespace": "npcs",
        "search": "nech",
    }


async def test_get_gameval_proxies_path(anon_client: AsyncClient) -> None:
    fake_client = _fake_client(Response(200, json=[{"entry_id": 8, "name": "npc_8"}]))
    with patch.object(osrs_cache, "httpx", _fake_httpx_module(fake_client)):
        resp = await anon_client.get("/osrs-cache/gamevals/npcs/8")

    assert resp.status_code == 200
    args, _ = fake_client.get.call_args
    assert args[0].endswith("/gamevals/npcs/8")


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
