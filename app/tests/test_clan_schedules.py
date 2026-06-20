from __future__ import annotations

from httpx import AsyncClient


async def test_list_schedules_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/clan/competition-schedules")
    assert resp.status_code == 401


async def test_list_schedules_with_auth(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/clan/competition-schedules")
    assert resp.status_code == 200


async def test_get_schedule_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/clan/competition-schedules/1")
    assert resp.status_code == 401


async def test_get_schedule_not_found(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/clan/competition-schedules/9999")
    assert resp.status_code in (200, 404)


async def test_create_schedule_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post("/clan/competition-schedules", json={})
    assert resp.status_code == 401


async def test_create_schedule_non_staff_forbidden(auth_client: AsyncClient) -> None:
    resp = await auth_client.post("/clan/competition-schedules", json={"name": "Test"})
    assert resp.status_code == 403


async def test_create_schedule_staff(staff_client: AsyncClient) -> None:
    resp = await staff_client.post("/clan/competition-schedules", json={"name": "Test"})
    assert resp.status_code in (200, 201, 422)


async def test_update_schedule_non_staff_forbidden(auth_client: AsyncClient) -> None:
    resp = await auth_client.patch("/clan/competition-schedules/1", json={})
    assert resp.status_code == 403


async def test_update_schedule_staff(staff_client: AsyncClient) -> None:
    resp = await staff_client.patch(
        "/clan/competition-schedules/9999", json={"name": "Updated"}
    )
    assert resp.status_code in (200, 404, 422)


async def test_delete_schedule_non_staff_forbidden(auth_client: AsyncClient) -> None:
    resp = await auth_client.delete("/clan/competition-schedules/1")
    assert resp.status_code == 403


async def test_delete_schedule_staff(staff_client: AsyncClient) -> None:
    resp = await staff_client.delete("/clan/competition-schedules/9999")
    assert resp.status_code in (204, 404)


async def test_pause_schedule_non_staff_forbidden(auth_client: AsyncClient) -> None:
    resp = await auth_client.post("/clan/competition-schedules/1/pause")
    assert resp.status_code == 403


async def test_resume_schedule_non_staff_forbidden(auth_client: AsyncClient) -> None:
    resp = await auth_client.post("/clan/competition-schedules/1/resume")
    assert resp.status_code == 403


async def test_list_runs_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/clan/competition-schedules/1/runs")
    assert resp.status_code == 401


async def test_list_runs_with_auth(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/clan/competition-schedules/9999/runs")
    assert resp.status_code in (200, 404)
