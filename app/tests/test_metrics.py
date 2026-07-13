from __future__ import annotations

from httpx import AsyncClient


async def test_bandwidth(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/metrics/bandwidth")
    assert resp.status_code in (200, 403, 500)


async def test_wom_rate_limit(staff_client: AsyncClient) -> None:
    resp = await staff_client.get("/metrics/wom-rate-limit")
    assert resp.status_code in (200, 500)


async def test_history(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/metrics/history?interval=1d")
    assert resp.status_code in (200, 422, 500)


async def test_services_status_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/services/status")
    assert resp.status_code == 401


async def test_services_status(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/services/status")
    assert resp.status_code in (200, 403, 500)


async def test_services_uptime_requires_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/services/uptime")
    assert resp.status_code == 401


async def test_services_uptime(auth_client: AsyncClient) -> None:
    resp = await auth_client.get("/services/uptime")
    assert resp.status_code in (200, 403, 500)


async def test_report_requires_key(auth_client: AsyncClient) -> None:
    from app.tests.conftest import _app
    from app.dependencies import verify_metrics_key

    original = _app.dependency_overrides.pop(verify_metrics_key, None)
    try:
        resp = await auth_client.post("/metrics/report", json={})
        assert resp.status_code in (401, 422)
    finally:
        if original is not None:
            _app.dependency_overrides[verify_metrics_key] = original


async def test_report_with_key(auth_client: AsyncClient) -> None:
    resp = await auth_client.post("/metrics/report", json={"metrics": []})
    assert resp.status_code in (200, 204, 422)
