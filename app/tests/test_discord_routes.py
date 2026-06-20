from __future__ import annotations

from httpx import AsyncClient


async def test_channels_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/discord/channels")
    assert resp.status_code == 401


async def test_channels_staff(staff_client: AsyncClient) -> None:
    resp = await staff_client.get("/discord/channels")
    assert resp.status_code in (200, 503)


async def test_emojis_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/discord/emojis")
    assert resp.status_code == 401


async def test_emojis_staff(staff_client: AsyncClient) -> None:
    resp = await staff_client.get("/discord/emojis")
    assert resp.status_code in (200, 503)


async def test_roles_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/discord/roles")
    assert resp.status_code == 401


async def test_roles_staff(staff_client: AsyncClient) -> None:
    resp = await staff_client.get("/discord/roles")
    assert resp.status_code in (200, 503)


async def test_members_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/discord/members?query=test")
    assert resp.status_code == 401


async def test_members_with_auth(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/discord/members?query=test")
    assert resp.status_code == 200
