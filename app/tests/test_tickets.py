from __future__ import annotations

from httpx import AsyncClient


async def test_ticket_config_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/tickets/config")
    assert resp.status_code == 401


async def test_ticket_config(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/tickets/config")
    assert resp.status_code == 200


async def test_ticket_config_panel_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/tickets/config/panel")
    assert resp.status_code == 401


async def test_ticket_config_panel(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/tickets/config/panel")
    assert resp.status_code == 200


async def test_ticket_type_config_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/tickets/config/1")
    assert resp.status_code == 401


async def test_ticket_type_config_not_found(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/tickets/config/9999")
    assert resp.status_code in (200, 404)


async def test_patch_ticket_type_config_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.patch("/tickets/config/1", json={})
    assert resp.status_code == 401


async def test_patch_ticket_type_config_non_staff_forbidden(
    auth_client: AsyncClient,
) -> None:
    resp = await auth_client.patch("/tickets/config/1", json={"enabled": True})
    assert resp.status_code == 403


async def test_patch_ticket_type_config_staff(staff_client: AsyncClient) -> None:
    resp = await staff_client.patch("/tickets/config/9999", json={"enabled": True})
    assert resp.status_code in (200, 404, 422)


async def test_upload_ticket_image_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post("/tickets/config/1/images")
    assert resp.status_code == 401


async def test_upload_ticket_image_non_staff(auth_client: AsyncClient) -> None:
    resp = await auth_client.post("/tickets/config/1/images")
    assert resp.status_code == 403


async def test_delete_ticket_image_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.delete("/tickets/config/1/images/test.png")
    assert resp.status_code == 401


async def test_delete_ticket_image_non_staff(auth_client: AsyncClient) -> None:
    resp = await auth_client.delete("/tickets/config/1/images/test.png")
    assert resp.status_code == 403
