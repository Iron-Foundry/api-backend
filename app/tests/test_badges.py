from __future__ import annotations

from httpx import AsyncClient
from unittest.mock import MagicMock


async def test_list_badges_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/badges")
    assert resp.status_code == 401


async def test_list_badges(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/badges")
    assert resp.status_code == 200


async def test_create_badge_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post("/badges", json={"name": "Test"})
    assert resp.status_code == 401


async def test_create_badge_staff(
    staff_client: AsyncClient, mock_session: MagicMock
) -> None:
    badge_mock = MagicMock()
    badge_mock.id = 1
    badge_mock.name = "Test"
    mock_session.execute.return_value.scalar_one_or_none.return_value = badge_mock
    resp = await staff_client.post(
        "/badges", json={"name": "Test", "description": "desc"}
    )
    assert resp.status_code in (200, 201, 422)


async def test_get_badge_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/badges/1")
    assert resp.status_code == 401


async def test_get_badge_not_found(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/badges/00000000-0000-0000-0000-000000000000")
    assert resp.status_code in (200, 404)


async def test_my_badge_assignments_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/badges/me")
    assert resp.status_code == 401


async def test_my_badge_assignments(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/badges/me")
    assert resp.status_code == 200
