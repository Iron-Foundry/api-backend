from __future__ import annotations

from httpx import AsyncClient


async def test_rank_mappings_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/config/rank-mappings")
    assert resp.status_code == 401


async def test_rank_mappings_read(staff_client: AsyncClient) -> None:
    resp = await staff_client.get("/config/rank-mappings")
    assert resp.status_code == 200


async def test_rank_mappings_read_non_staff(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/config/rank-mappings")
    assert resp.status_code == 403


async def test_rank_mappings_update_non_staff(auth_client: AsyncClient) -> None:
    resp = await auth_client.put("/config/rank-mappings", json={"mappings": []})
    assert resp.status_code == 403


async def test_rank_mappings_update_staff(staff_client: AsyncClient) -> None:
    resp = await staff_client.put("/config/rank-mappings", json={"mappings": []})
    assert resp.status_code == 200


async def test_page_permissions_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/config/page-permissions")
    assert resp.status_code == 401


async def test_page_permissions_read(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/config/page-permissions")
    assert resp.status_code == 200


async def test_page_permissions_update_staff(staff_client: AsyncClient) -> None:
    resp = await staff_client.put("/config/page-permissions", json={"pages": {}})
    assert resp.status_code == 200


async def test_admin_bypass_roles_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/config/admin-bypass-roles")
    assert resp.status_code == 401


async def test_admin_bypass_roles_read(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/config/admin-bypass-roles")
    assert resp.status_code == 200


async def test_admin_bypass_roles_update_staff(staff_client: AsyncClient) -> None:
    resp = await staff_client.put("/config/admin-bypass-roles", json={"roles": []})
    assert resp.status_code in (200, 403)


async def test_service_toggles_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/config/services/toggles")
    assert resp.status_code == 401


async def test_service_toggles_read(staff_client: AsyncClient) -> None:
    resp = await staff_client.get("/config/services/toggles")
    assert resp.status_code == 200


async def test_discord_roles_config_read(staff_client: AsyncClient) -> None:
    resp = await staff_client.get("/config/discord-roles")
    assert resp.status_code == 200


async def test_ranking_config_read(staff_client: AsyncClient) -> None:
    resp = await staff_client.get("/config/ranking")
    assert resp.status_code == 200


async def test_ticket_features_read(staff_client: AsyncClient) -> None:
    resp = await staff_client.get("/config/ticket-features")
    assert resp.status_code == 200


async def test_panel_config_read(staff_client: AsyncClient) -> None:
    resp = await staff_client.get("/config/panel")
    assert resp.status_code == 200


async def test_notification_categories_read(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/config/party-notification-categories")
    assert resp.status_code == 200


async def test_discord_feature_action_log_read(staff_client: AsyncClient) -> None:
    resp = await staff_client.get("/config/discord-feature/action-log")
    assert resp.status_code == 200
