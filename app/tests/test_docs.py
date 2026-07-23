from __future__ import annotations

from httpx import AsyncClient


async def test_scalar_docs_served(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/docs")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "scalar" in resp.text.lower()


async def test_openapi_available(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/openapi.json")
    assert resp.status_code == 200
    assert resp.json()["info"]["title"] == "The Foundry API"


async def test_redoc_disabled(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/redoc")
    assert resp.status_code == 404
