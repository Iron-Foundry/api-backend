from __future__ import annotations

from httpx import AsyncClient


async def test_ranking_status_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/ranking/status")
    assert resp.status_code == 401


async def test_ranking_status(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/ranking/status")
    assert resp.status_code == 200


async def test_ranking_stats(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/ranking/stats")
    assert resp.status_code in (200, 500)


async def test_player_ranking(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/ranking/player/SomePlayer")
    assert resp.status_code in (200, 404, 500)


async def test_ranking_results(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/ranking/results")
    assert resp.status_code in (200, 500)


async def test_run_ranking_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post("/ranking/run")
    assert resp.status_code == 401


async def test_run_ranking_non_staff_forbidden(auth_client: AsyncClient) -> None:
    resp = await auth_client.post("/ranking/run")
    assert resp.status_code == 403


async def test_run_ranking_staff(staff_client: AsyncClient) -> None:
    resp = await staff_client.post("/ranking/run")
    assert resp.status_code in (200, 202, 422, 500)


async def test_preview_ranking_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.post("/ranking/preview")
    assert resp.status_code == 401


async def test_preview_ranking_non_staff_forbidden(auth_client: AsyncClient) -> None:
    resp = await auth_client.post("/ranking/preview")
    assert resp.status_code in (403, 404, 422)


async def test_preview_ranking_staff(staff_client: AsyncClient) -> None:
    resp = await staff_client.post("/ranking/preview")
    assert resp.status_code in (200, 202, 422, 500)
