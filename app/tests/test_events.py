from __future__ import annotations

from httpx import AsyncClient


async def test_ccingest_missing_key_header(auth_client: AsyncClient) -> None:
    """Missing required verification-code header → 401 or 422."""
    from app.tests.conftest import _app
    from app.dependencies import verify_metrics_key

    original = _app.dependency_overrides.pop(verify_metrics_key, None)
    try:
        resp = await auth_client.post(
            "/ccingest",
            json={"type": "broadcast", "message": "test"},
        )
        assert resp.status_code in (401, 422)
    finally:
        if original is not None:
            _app.dependency_overrides[verify_metrics_key] = original


async def test_ccingest_with_key(auth_client: AsyncClient) -> None:
    resp = await auth_client.post(
        "/ccingest",
        json={"type": "broadcast", "message": "test message", "player": "TestPlayer"},
    )
    assert resp.status_code in (200, 204, 422)


async def test_ccingest_missing_body(auth_client: AsyncClient) -> None:
    resp = await auth_client.post("/ccingest")
    assert resp.status_code == 422
