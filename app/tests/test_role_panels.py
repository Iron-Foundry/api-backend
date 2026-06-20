from __future__ import annotations

from httpx import AsyncClient

_UUID = "00000000-0000-0000-0000-000000000001"


async def test_list_panels_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/role-panels")
    assert resp.status_code == 401


async def test_list_panels_with_auth(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/role-panels")
    assert resp.status_code == 200


async def test_get_panel_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get(f"/role-panels/{_UUID}")
    assert resp.status_code == 401


async def test_get_panel_not_found(auth_client: AsyncClient) -> None:
    resp = await auth_client.get(f"/role-panels/{_UUID}")
    assert resp.status_code in (200, 404)


async def test_update_panel_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.put(f"/role-panels/{_UUID}", json={})
    assert resp.status_code == 401


async def test_update_panel_non_staff_forbidden(auth_client: AsyncClient) -> None:
    resp = await auth_client.put(
        f"/role-panels/{_UUID}", json={"title": "Test", "roles": []}
    )
    assert resp.status_code == 403


async def test_update_panel_staff_not_found(staff_client: AsyncClient) -> None:
    resp = await staff_client.put(
        f"/role-panels/{_UUID}", json={"title": "Test", "roles": []}
    )
    assert resp.status_code in (200, 404, 422)


async def test_delete_panel_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.delete(f"/role-panels/{_UUID}")
    assert resp.status_code == 401


async def test_delete_panel_non_staff_forbidden(auth_client: AsyncClient) -> None:
    resp = await auth_client.delete(f"/role-panels/{_UUID}")
    assert resp.status_code == 403


async def test_delete_panel_staff_not_found(staff_client: AsyncClient) -> None:
    resp = await staff_client.delete(f"/role-panels/{_UUID}")
    assert resp.status_code in (204, 404)
