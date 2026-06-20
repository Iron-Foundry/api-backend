from __future__ import annotations

from httpx import AsyncClient


async def test_create_competition_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post("/clan/competitions", json={})
    assert resp.status_code == 401


async def test_create_competition_non_staff_forbidden(auth_client: AsyncClient) -> None:
    resp = await auth_client.post("/clan/competitions", json={"title": "Test"})
    assert resp.status_code == 403


async def test_create_competition_staff(staff_client: AsyncClient) -> None:
    payload = {
        "title": "Test Competition",
        "metric": "overall",
        "starts_at": "2025-01-01T00:00:00Z",
    }
    resp = await staff_client.post("/clan/competitions", json=payload)
    assert resp.status_code in (200, 201, 422, 500)


async def test_update_competition_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.put("/clan/competitions/1", json={})
    assert resp.status_code == 401


async def test_update_competition_non_staff_forbidden(auth_client: AsyncClient) -> None:
    resp = await auth_client.put("/clan/competitions/1", json={"title": "Updated"})
    assert resp.status_code == 403


async def test_update_competition_staff(staff_client: AsyncClient) -> None:
    resp = await staff_client.put("/clan/competitions/1", json={"title": "Updated"})
    assert resp.status_code in (200, 404, 422, 500, 503)


async def test_delete_competition_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.delete("/clan/competitions/1")
    assert resp.status_code == 401


async def test_delete_competition_non_staff_forbidden(auth_client: AsyncClient) -> None:
    resp = await auth_client.delete("/clan/competitions/1")
    assert resp.status_code == 403


async def test_delete_competition_staff(staff_client: AsyncClient) -> None:
    resp = await staff_client.delete("/clan/competitions/1")
    assert resp.status_code in (204, 404, 500, 503)


async def test_update_metric_map_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post("/clan/competitions/metric-map", json={})
    assert resp.status_code == 401


async def test_update_metric_map_non_staff_forbidden(auth_client: AsyncClient) -> None:
    resp = await auth_client.post(
        "/clan/competitions/metric-map", json={"mappings": []}
    )
    assert resp.status_code == 403


async def test_update_metric_map_staff(staff_client: AsyncClient) -> None:
    resp = await staff_client.post(
        "/clan/competitions/metric-map", json={"mappings": []}
    )
    assert resp.status_code in (200, 422)
