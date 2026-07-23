"""Boot the real app through its lifespan against live Postgres + Valkey."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def test_health_ok(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_db_backed_get_returns_empty(client: AsyncClient) -> None:
    """A DB-backed list endpoint responds 200 with real (empty) data,
    proving the engine + session factory were wired by the lifespan."""
    resp = await client.get("/badges/")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
