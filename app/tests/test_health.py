from __future__ import annotations

from httpx import AsyncClient


async def test_health(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
